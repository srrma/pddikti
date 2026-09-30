"""Command line entry point."""

from __future__ import annotations

import argparse
import datetime
import os
import sys

from pddikti import api, render

SERIES_ROWS = 12


def _first_of(row: dict, *keys: str):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def semester_record(row: dict) -> dict:
    return {"title": render.dash(row.get("semester")),
            "fields": [("Semester", row.get("semester")),
                       ("Mahasiswa", render.number(row.get("jumlah_mahasiswa"))),
                       ("Dosen", render.number(row.get("jumlah_dosen"))),
                       ("Dosen mengajar", render.number(row.get("jumlah_dosen_ajar")))],
            "raw": row}


def current_semester(today: datetime.date | None = None) -> str:
    """Ganjil runs August to January, genap February to July. The site rejects YYYY alone."""
    day = today or datetime.date.today()
    return f"{day.year}{1 if day.month >= 8 or day.month <= 1 else 2}"


def previous_semester(code: str) -> str:
    year, half = int(code[:4]), code[4]
    return f"{year - 1}2" if half == "1" else f"{year}1"


def collect_terms(args) -> list[str]:
    terms = list(args.terms)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    terms.append(line)
    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    seen, unique = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pddikti",
        description="Query PDDIKTI, the Indonesian higher-education registry.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("terms", nargs="*", help="one or more search terms")
    common.add_argument("--file", metavar="PATH", help="read terms from a file, one per line")
    common.add_argument("--stdin", action="store_true", help="read terms from standard input")
    common.add_argument("-d", "--detail", action="store_true", help="expand each hit in full")
    common.add_argument("--match", type=int, default=1, metavar="N", help="which hit to expand")
    common.add_argument("--limit", type=int, default=10, metavar="N", help="hits per term, max 100")
    common.add_argument("--jobs", type=int, default=int(os.environ.get("PDDIKTI_JOBS", 4)),
                        metavar="N", help="concurrent requests")
    common.add_argument("--delay", type=float, default=0.0, metavar="SEC",
                        help="pause before each request")
    common.add_argument("--timeout", type=float, default=None, metavar="SEC")
    common.add_argument("--table", action="store_true", help="force a table for every view")
    common.add_argument("--json", action="store_true", help="print the upstream JSON")
    common.add_argument("--count", action="store_true", help="print one count per term")
    common.add_argument("-o", "--out", metavar="PATH",
                        help="write to a file, or - for standard output")
    common.add_argument("--format", choices=render.EXPORT_FORMATS,
                        help="export format, otherwise taken from the file extension")
    common.add_argument("--no-color", action="store_true")
    common.add_argument("--semester", metavar="CODE",
                        help="semester code such as 20261, otherwise the current one")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pt", parents=[common], help="search universities")
    sub.add_parser("prodi", parents=[common], help="search study programs")
    sub.add_parser("mhs", parents=[common], help="search students")
    sub.add_parser("dosen", parents=[common], help="search lecturers")
    sub.add_parser("all", parents=[common], help="search all four at once")
    sub.add_parser("stats", parents=[common], help="national totals and field breakdown")

    pt = sub.choices["pt"]
    pt.add_argument("--logo", metavar="PATH", help="download the university logo to a file")
    pt.add_argument("--provinsi", default="", help="exact PDDIKTI label, e.g. 'Prov. Jawa Barat'")
    pt.add_argument("--akreditasi", default="")
    pt.add_argument("--jenis", default="", help="PTN or PTS")
    pt.add_argument("--all-pages", action="store_true", help="walk every page of a filter query")
    pt.add_argument("--prodi", action="store_true", help="with -d, list the study programs too")

    prodi = sub.choices["prodi"]
    prodi.add_argument("--pt", dest="pt", metavar="NAME", help="scope the search to a university")
    prodi.add_argument("--dosen", action="store_true",
                      help="with -d, list the homebase lecturers for the semester")

    mhs = sub.choices["mhs"]
    mhs.add_argument("--nim", metavar="NIM", help="look up one student by NIM")
    return parser


def hint_for(args) -> str:
    filters = [name for name in ("provinsi", "akreditasi", "jenis")
               if getattr(args, name, "")]
    if not filters:
        return ""
    return (" PDDIKTI matches filters literally, so a label that differs from the site's "
            "wording returns nothing: " + ", ".join("--" + name for name in filters))


def run_term(client, args, term: str):
    """One term, one command: returns the raw hits."""
    if args.command == "pt":
        return pt_hits(client, args, term)
    if args.command == "prodi":
        return api.search(client, "prodi", term)[: args.limit]
    if args.command == "mhs":
        return api.search(client, "mhs", term)[: args.limit]
    if args.command == "dosen":
        return api.search(client, "dosen", term)[: args.limit]
    return api.search_all(client, term)


FILTERS = ("provinsi", "akreditasi", "jenis")


def pt_hits(client, args, term: str) -> list:
    """Universities go through the faceted endpoint: it is the only one that returns the
    city, province, accreditation and program count, and the only one that paginates."""
    limit = min(args.limit, 100)
    filters = {name: getattr(args, name) for name in FILTERS}
    if not term and not any(filters.values()):
        return api.pt_filter(client, limit=limit)["data"]
    rows, page, pages = [], 1, 1
    while True:
        result = api.pt_filter(client, nama=term, limit=limit, page=page, **filters)
        rows.extend(result["data"])
        pages = result.get("totalPages") or 1
        if not args.all_pages or page >= pages or page >= 100:
            break
        page += 1
    if rows or not term.isdigit():
        return rows
    # A numeric code matches no name, so it is looked up in the full institution list.
    return [row for row in api.pt_locations(client)
            if str(row.get("kode", "")).strip() == term]


def build_pt_sections(client, args, term: str, hits: list) -> list:
    if not args.detail:
        title = "universities" + (f" matching {term!r}" if term else "")
        applied = [f"{name}={getattr(args, name)}" for name in FILTERS if getattr(args, name)]
        if applied:
            title += " (" + ", ".join(applied) + ")"
        return [render.section(title, [render.pt_record(hit) for hit in hits], hits,
                               render.SEARCH_COLUMNS["pt"])]
    hit = hits[args.match - 1] if len(hits) >= args.match else None
    if hit is None:
        return []
    stats = api.pt_stats(client, hit["id_sp"] if "id_sp" in hit else hit["id"])
    detail = stats["detail"]
    record = render.pt_record({**hit, **detail})
    record["fields"] = [
        ("Kode", detail.get("kode_pt")),
        ("Singkatan", detail.get("nm_singkat") or detail.get("nama_singkat")),
        ("Nama", detail.get("nama_pt")),
        ("Kelompok", detail.get("kelompok")),
        ("Pembina", detail.get("pembina")),
        ("Alamat", detail.get("alamat")),
        ("Kode pos", detail.get("kode_pos")),
        ("Telepon", detail.get("no_tel")),
        ("Email", detail.get("email")),
        ("Web", detail.get("website")),
        ("Program studi", render.number(stats["counts"].get("prodi"))),
        ("Mahasiswa", render.number(stats["counts"].get("mahasiswa"))),
        ("Dosen", render.number(stats["counts"].get("dosen"))),
        ("Rasio", (stats.get("rasio") or {}).get("rasio")
         if isinstance(stats.get("rasio"), dict) else stats.get("rasio")),
        ("Lulus", render.number((stats.get("graduation_rate") or {}).get("graduation_rate")
                                if isinstance(stats.get("graduation_rate"), dict) else None) + " %"),
        ("Rata-rata lulus", render.number((stats.get("kelulusan") or {}).get("mean_jumlah_lulus")
                                          if isinstance(stats.get("kelulusan"), dict) else None)),
        ("Rata-rata baru", render.number((stats.get("kelulusan") or {}).get("mean_jumlah_baru")
                                         if isinstance(stats.get("kelulusan"), dict) else None)),
        ("Biaya kuliah", (stats.get("cost_range") or {}).get("range_biaya_kuliah")
         if isinstance(stats.get("cost_range"), dict) else None),
        ("Masa studi", "; ".join(f"{item.get('jenjang')} {item.get('mean_masa_studi')}"
                                 for item in stats.get("waktu_studi") or []
                                 if isinstance(item, dict))),
        ("Riwayat nama", "; ".join(str(item.get("nama_pt", item)) for item in
                                 stats.get("name_histories") or [] if item)),
    ]
    sections = [render.section(detail.get("nama_pt") or term, [record], stats)]
    if args.prodi:
        semester, programs = fetch_prodi(client, hit, args.semester)
        sections.append(render.section(
            f"study programs, semester {semester}",
            [render.prodi_record(row) for row in programs], programs,
            ("Kode", "Jenjang", "Program studi", "Akreditasi", "Status", "Dosen",
             "Mahasiswa", "Rasio")))
    return sections


def fetch_prodi(client, pt_hit: dict, semester: str | None) -> tuple[str, list]:
    id_sp = pt_hit.get("id_sp") or pt_hit.get("id")
    code = semester or current_semester()
    programs = api.pt_prodi(client, id_sp, code)
    if not programs and not semester:
        code = previous_semester(code)
        programs = api.pt_prodi(client, id_sp, code)
    return code, programs


def scoped_prodi(client, args, term: str) -> tuple[str, list]:
    """A study-program search inside one university, using that university's own list."""
    hits = api.search(client, "pt", args.pt)[:1]
    if not hits:
        raise api.PddiktiError(f"no university matches {args.pt!r}")
    semester, programs = fetch_prodi(client, hits[0], args.semester)
    needle = term.lower()
    matched = [row for row in programs
               if not needle or needle in render.dash(row.get("nama_prodi")).lower()
               or needle in render.dash(row.get("kode_prodi")).lower()]
    return semester, matched[: args.limit]


def build_sections(client, args, term: str, hits) -> list:
    """Every section a term produced. The term is recorded on each one so an exported row
    can be traced back to the search that produced it."""
    return [dict(group, source=term) for group in sections_for_term(client, args, term, hits)]


def sections_for_term(client, args, term: str, hits) -> list:

    if args.command == "pt":
        return build_pt_sections(client, args, term, hits)
    if args.command == "prodi":
        semester, rows = (scoped_prodi(client, args, term) if args.pt
                          else (term, hits[: args.limit]))
        title = (f"study programs at {args.pt!r} matching {term!r}, semester {semester}"
                 if args.pt else f"study programs matching {term!r}")
        if not args.detail:
            return [render.section(title, [render.prodi_record(r) for r in rows], rows,
                                   render.SEARCH_COLUMNS["prodi"])]
        row = rows[args.match - 1] if len(rows) >= args.match else None
        if row is None:
            return []
        detail = api.prodi_detail(client, row["id_sms"])
        desc = detail.get("desc") if isinstance(detail.get("desc"), dict) else {}
        cost = detail.get("cost_range") if isinstance(detail.get("cost_range"), dict) else {}
        ratio = detail.get("rasio") if isinstance(detail.get("rasio"), dict) else {}
        merged = {**row, **detail}
        record = render.prodi_record(merged)
        record["fields"] = [
            ("Kode", detail.get("kode_prodi")),
            ("Program studi", detail.get("nama_prodi")),
            ("Jenjang", _first_of(merged, "jenj_didik", "jenjang_prodi")),
            ("Bidang ilmu", detail.get("kel_bidang")),
            ("Perguruan tinggi", detail.get("nama_pt")),
            ("Status", detail.get("status")),
            ("Akreditasi", detail.get("akreditasi")),
            ("Akreditasi internasional", detail.get("akreditasi_internasional")),
            ("Status akreditasi", detail.get("status_akreditasi")),
            ("Berdiri", (detail.get("tgl_berdiri") or "")[:10] or None),
            ("SK penyelenggara", detail.get("sk_selenggara")),
            ("Dosen", render.number(_first_of(merged, "jumlah_dosen") or desc.get("jumlah_dosen"))),
            ("Dosen mengajar", render.number(desc.get("jumlah_dosen_ajar"))),
            ("Mahasiswa", render.number(_first_of(merged, "jumlah_mahasiswa"))),
            ("Pendaftar", render.number(desc.get("jumlah_pendaftar"))),
            ("Diterima", render.number(desc.get("jumlah_diterima"))),
            ("Rasio", ratio.get("rasio_dosen_mahasiswa") or _first_of(merged, "rasio")),
            ("Rasio terima daftar", desc.get("rasio_terima_daftar")),
            ("Biaya kuliah", cost.get("range_biaya_kuliah")),
            ("Alamat", detail.get("alamat")),
            ("Kota", detail.get("kab_kota")),
            ("Provinsi", detail.get("provinsi")),
            ("Telepon", detail.get("no_tel")),
            ("Web", detail.get("website")),
            ("Email", detail.get("email")),
        ]
        sections = [render.section(detail.get("nama_prodi") or term, [record], detail)]
        if render.strip_html(desc.get("deskripsi_singkat")):
            sections.append(render.section("description", [{
                "title": "description",
                "fields": [("Deskripsi", render.strip_html(desc["deskripsi_singkat"]))],
                "raw": desc}], desc))
        if args.dosen:
            semester = args.semester or current_semester()
            roster = api.prodi_dosen(client, row["id_sms"], semester)
            if roster:
                sections.append(render.section(
                    f"homebase lecturers, semester {semester}",
                    [dosen_roster_record(item) for item in roster], roster,
                    ("NIDN", "NUPTK", "Nama", "Pendidikan", "Ikatan kerja", "Status")))
        series = [row for row in detail.get("num_students_lecturers") or []
                  if isinstance(row, dict)]
        if series:
            shown = series[:SERIES_ROWS]
            title = "students and lecturers per semester"
            if len(series) > len(shown):
                title += f" (most recent {len(shown)} of {len(series)})"
            sections.append(render.section(
                title, [semester_record(row) for row in shown], shown,
                ("Semester", "Mahasiswa", "Dosen", "Dosen mengajar")))
        return sections
    if args.command == "mhs":
        if not args.detail:
            return [render.section(f"students matching {term!r}",
                                   [render.mhs_record(h) for h in hits], hits,
                                   render.SEARCH_COLUMNS["mhs"])]
        hit = hits[args.match - 1] if len(hits) >= args.match else None
        if hit is None:
            return []
        detail = api.mhs_detail(client, hit["id"])
        record = render.mhs_record({**hit, **detail})
        sections = [render.section(detail.get("nama") or term, [record], detail)]
        return sections
    if args.command == "dosen":
        if not args.detail:
            return [render.section(f"lecturers matching {term!r}",
                                   [render.dosen_record(h) for h in hits], hits,
                                   render.SEARCH_COLUMNS["dosen"])]
        hit = hits[args.match - 1] if len(hits) >= args.match else None
        if hit is None:
            return []
        detail = api.dosen_detail(client, hit["id"])
        record = render.dosen_record({**hit, **detail})
        sections = [render.section(detail.get("nama_dosen") or term, [record], detail)]
        for key, label, columns, fields in (
            ("study_history", "education history",
             ("Tahun masuk", "Tahun lulus", "Jenjang", "Program studi", "Gelar", "NIDN"),
             ("tahun_masuk", "tahun_lulus", "jenjang", "nama_prodi", "gelar_akademik", "nidn")),
            ("teaching_history", "subjects taught",
             ("Semester", "Kode", "Mata kuliah", "SKS", "Kelas"),
             ("nama_semester", "kode_matkul", "nama_matkul", "sks", "nama_kelas")),
        ):
            rows = [row for row in detail.get(key) or [] if isinstance(row, dict)]
            if not rows:
                continue
            sections.append(render.section(
                label, [history_record(row, columns, fields) for row in rows], rows, columns))
        for key, label, columns, fields in (
            ("penelitian", "research", ("Tahun", "Judul", "Sumber dana"),
             ("tahun", "judul", "sumber_dana")),
            ("pengabdian", "community service", ("Tahun", "Judul", "Sumber dana"),
             ("tahun", "judul", "sumber_dana")),
            ("karya", "works", ("Tahun", "Judul", "Jenis"),
             ("tahun", "judul", "jenis")),
            ("paten", "patents", ("Tahun", "Judul", "Nomor"),
             ("tahun", "judul", "nomor")),
        ):
            rows = [row for row in detail.get(key) or [] if isinstance(row, dict)]
            if rows:
                sections.append(render.section(
                    label, [history_record(row, columns, fields) for row in rows], rows, columns))
        return sections
    return build_all_sections(term, hits)


def dosen_roster_record(row: dict) -> dict:
    return {"title": render.dash(row.get("nama_dosen")),
            "fields": [("NIDN", row.get("nidn")), ("NUPTK", row.get("nuptk")),
                       ("Nama", row.get("nama_dosen")),
                       ("Pendidikan", row.get("pendidikan")),
                       ("Ikatan kerja", row.get("ikatan_kerja")),
                       ("Status", row.get("status_aktif"))],
            "raw": row}


def history_record(row: dict, columns: tuple, fields: tuple) -> dict:
    # A year of 0 is the server's way of saying it has no year, not the year zero.
    values = [(label, row.get(key) or None) for label, key in zip(columns, fields)]
    return {"title": render.dash(row.get(fields[0])), "fields": values, "raw": row}


def build_all_sections(term: str, hits) -> list:
    if not isinstance(hits, dict):
        return []
    makers = {"pt": render.pt_record, "prodi": render.prodi_record,
              "mhs": render.mhs_record, "dosen": render.dosen_record}
    labels = {"pt": "universities", "prodi": "study programs",
              "mhs": "students", "dosen": "lecturers"}
    sections = []
    for kind in ("pt", "prodi", "mhs", "dosen"):
        rows = hits.get(kind) or []
        if not rows:
            continue
        sections.append(render.section(f"{labels[kind]} matching {term!r}",
                                       [makers[kind](row) for row in rows], rows,
                                       render.ALL_COLUMNS[kind]))
    return sections


def stats_sections(client) -> list:
    data = api.beranda(client)
    totals = {
        "Perguruan tinggi": data.get("pt", {}).get("jumlah"),
        "Program studi": data.get("prodi", {}).get("jumlah"),
        "Mahasiswa": data.get("mahasiswa", {}).get("jumlah_mahasiswa"),
        "Dosen": data.get("dosen", {}).get("jumlah_dosen"),
    }
    record = {"title": "PDDIKTI national totals",
              "fields": [(label, render.number(value)) for label, value in totals.items()],
              "raw": data}
    breakdown = data.get("bidang_ilmu") or []
    sections = [render.section("", [record], data)]
    if breakdown:
        sections.append(render.section(
            "by field of study",
            [{"title": row.get("bidang_ilmu", "-"),
              # Sent as a string with an Indonesian decimal comma, so it is shown as sent
              # rather than reformatted next to a comma thousands separator.
              "fields": [("Bidang ilmu", row.get("bidang_ilmu")),
                         ("Total mahasiswa", render.number(row.get("total_mahasiswa"))),
                         ("Kelulusan", row.get("persentase_kelulusan"))],
              "raw": row} for row in breakdown], breakdown,
            ("Bidang ilmu", "Total mahasiswa", "Kelulusan")))
    return sections


def export_format(path: str | None, override: str | None) -> str | None:
    if override:
        return override
    if not path or path == "-":
        return None
    extension = os.path.splitext(path)[1].lstrip(".").lower()
    return extension if extension in render.EXPORT_FORMATS else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = api.Client(timeout=args.timeout, delay=args.delay)

    if args.command == "pt" and args.logo:
        return download_logo(client, args)

    if args.command == "stats":
        sections = stats_sections(client)
        return finish(args, sections, "national totals")

    if args.command == "mhs" and args.nim:
        args.terms = [args.nim]
    terms = collect_terms(args)
    if not terms and not (args.command == "pt" and
                          (args.provinsi or args.akreditasi or args.jenis)):
        print("give at least one search term, --file, --stdin, or --nim", file=sys.stderr)
        return 2

    failures = 0
    empty: list[str] = []
    sections: list = []
    show_progress = len(terms) > 1 and sys.stderr.isatty() and not (args.count or args.json)

    def work(term: str):
        return run_term(client, args, term)

    results = client.run_all(args.jobs, work, terms)
    for index, (term, outcome) in enumerate(zip(terms, results), start=1):
        status, payload = outcome
        if status == "error":
            failures += 1
            print(f"! {term}: {payload}", file=sys.stderr)
            continue
        if args.count:
            size = len(payload) if isinstance(payload, list) else sum(
                len(v) for v in payload.values() if isinstance(v, list)) if isinstance(
                payload, dict) else 0
            print(f"{term}\t{size}")
            if size == 0:
                empty.append(term)
            continue
        term_sections = build_sections(client, args, term, payload)
        if not any(group["records"] for group in term_sections):
            empty.append(term)
        sections.extend(term_sections)
        if show_progress:
            print(f"\r{index}/{len(terms)}", end="", file=sys.stderr, flush=True)
    if show_progress:
        print("", file=sys.stderr)

    if args.count:
        return 1 if (failures or empty) else 0
    found = any(group["records"] for group in sections)
    if not found and failures == len(terms):
        return 3
    if empty and not found:
        # One message for the whole run, so a bulk miss does not repeat itself per term.
        return finish(args, sections, ", ".join(empty[:3]) + ("…" if len(empty) > 3 else ""),
                      failures + len(empty))
    sys.stdout.flush()
    for term in empty:
        print(f"no results for {term!r}{hint_for(args)}", file=sys.stderr)
    return finish(args, sections, ", ".join(terms[:3]) + ("…" if len(terms) > 3 else ""),
                  failures + len(empty))


def download_logo(client, args) -> int:
    if not args.terms:
        print("give a university name or code, or --file", file=sys.stderr)
        return 2
    hits = pt_hits(client, args, args.terms[0])
    if len(hits) < args.match:
        print(f"no results for {args.terms[0]!r}", file=sys.stderr)
        return 1
    hit = hits[args.match - 1]
    with open(args.logo, "wb") as handle:
        handle.write(client.get_bytes(f"/pt/logo/{hit.get('id_sp') or hit.get('id')}"))
    print(f"wrote {args.logo}", file=sys.stderr)
    return 0


def finish(args, sections: list, source: str, failures: int = 0) -> int:
    records = [record for group in sections for record in group["records"]]
    fmt = export_format(args.out, args.format)
    if fmt:
        sys.stdout.flush()
        render.write_export(sections, args.out, fmt)
        if args.out != "-":
            print(f"wrote {len(records)} records to {args.out}", file=sys.stderr)
        return 1 if (failures or not records) else 0
    if args.json:
        print(render.to_json(sections))
    elif not records:
        print(f"no results for {source!r}{hint_for(args)}", file=sys.stderr)
    else:
        render.print_sections(sections, colour=render.colour_enabled(args.no_color),
                              as_table=args.table, source=source)
    return 1 if (failures or not records) else 0
