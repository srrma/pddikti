"""Turning API payloads into records, and records into terminal or file output."""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import shutil
import sys

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

EXPORT_FORMATS = ("json", "csv", "tsv", "md", "html")


def colour_enabled(no_color: bool = False) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def width() -> int:
    return max(40, shutil.get_terminal_size((100, 24)).columns)


def dash(value) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return dash(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.1f}"


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def wrap(text: str, limit: int) -> list[str]:
    """Used for prose, which has to stay readable rather than lose its ending."""
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > limit:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines or [""]


def strip_html(text) -> str:
    """PDDIKTI returns rich-text fields as HTML fragments."""
    if not text:
        return ""
    plain = re.sub(r"<[^>]+>", " ", str(text))
    return " ".join(plain.split())


def _first(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _string(value) -> str:
    if isinstance(value, list):
        parts = [dash(item.get("nama", item)) if isinstance(item, dict) else str(item)
                 for item in value]
        return "; ".join(parts)
    return dash(value)


def pt_record(row: dict) -> dict:
    return {
        "title": dash(_first(row, "nama_pt", "nama")),
        "fields": [
            ("Nama", _first(row, "nama_pt", "nama")),
            ("Kode", _first(row, "kode_pt", "kode")),
            ("Singkatan", _first(row, "nama_singkat", "singkat")),
            ("Jenis", _first(row, "jenis_pt", "jenis", "kelompok")),
            ("Provinsi", _first(row, "provinsi_pt", "provinsi")),
            ("Kota", _first(row, "kab_kota_pt", "kab_kota")),
            ("Status", _first(row, "status_pt", "status")),
            ("Akreditasi", row.get("akreditasi")),
            ("Pembina", row.get("pembina")),
            ("Program studi", number(_first(row, "jumlah_prodi", "jumlah_prodi_pt"))),
            ("Biaya kuliah", _first(row, "range_biaya_kuliah", "biaya")),
        ],
        "raw": row,
    }


def prodi_record(row: dict) -> dict:
    return {
        "title": dash(_first(row, "nama_prodi", "nama")),
        "fields": [
            ("Kode", row.get("kode_prodi")),
            ("Program studi", _first(row, "nama_prodi", "nama")),
            ("Jenjang", _first(row, "jenjang_prodi", "jenj_didik", "jenjang")),
            ("Perguruan tinggi", _first(row, "nama_pt", "pt")),
            ("Singkatan", _first(row, "nm_singkat_pt", "pt_singkat", "sinkatan_pt")),
            ("Akreditasi", row.get("akreditasi")),
            ("Status", row.get("status_prodi")),
            ("Dosen", number(_first(row, "jumlah_dosen", "jumlah_dosen_total"))),
            ("Mahasiswa", number(row.get("jumlah_mahasiswa"))),
            ("Rasio", row.get("rasio")),
        ],
        "raw": row,
    }


def mhs_record(row: dict) -> dict:
    return {
        "title": dash(row.get("nama")),
        "fields": [
            ("Nama", row.get("nama")),
            ("NIM", row.get("nim")),
            ("Jenis kelamin", row.get("jenis_kelamin")),
            ("Jenjang", row.get("jenjang")),
            ("Program studi", _first(row, "nama_prodi", "prodi")),
            ("Perguruan tinggi", _first(row, "nama_pt", "pt")),
            ("Status", _first(row, "status_saat_ini", "status")),
            ("Masuk", (row.get("tanggal_masuk") or "")[:10] or None),
        ],
        "raw": row,
    }


def dosen_record(row: dict) -> dict:
    return {
        "title": dash(_first(row, "nama_dosen", "nama")),
        "fields": [
            ("Nama", _first(row, "nama_dosen", "nama")),
            ("NIDN", row.get("nidn")),
            ("NUPTK", row.get("nuptk")),
            ("Program studi", row.get("nama_prodi")),
            ("Perguruan tinggi", _first(row, "nama_pt", "pt")),
            ("Jenis kelamin", row.get("jenis_kelamin")),
            ("Pendidikan", _first(row, "pendidikan_tertinggi", "pendidikan")),
            ("Jabatan", row.get("jabatan_akademik")),
            ("Ikatan kerja", row.get("status_ikatan_kerja")),
            ("Aktivitas", _first(row, "status_aktivitas", "status_aktif")),
        ],
        "raw": row,
    }


# A short column header may stand for a longer field label.
ALIASES = {"Prodi": "Program studi", "PT": "Perguruan tinggi"}

SEARCH_COLUMNS = {
    "pt": ("Nama", "Singkatan", "Jenis", "Kota", "Akreditasi", "Prodi"),
    "prodi": ("Jenjang", "Program studi", "Perguruan tinggi"),
    "mhs": ("NIM", "Nama", "Perguruan tinggi", "Program studi"),
    "dosen": ("Nama", "NIDN", "NUPTK", "Perguruan tinggi", "Program studi"),
}

# The combined search returns a university with only its code, abbreviation and name, so
# the wide column set would render as a row of dashes.
ALL_COLUMNS = dict(SEARCH_COLUMNS, pt=("Kode", "Nama"))


def section(title: str, records: list, raw: object, columns: tuple | None = None,
            source: str = "") -> dict:
    return {"title": title, "records": records, "raw": raw, "columns": columns,
            "source": source}


def render_card(record: dict, colour: bool, rule: int) -> list[str]:
    title = record["title"]
    fields = [(_label, _string(value)) for _label, value in record["fields"]
              if _string(value) != title]
    if colour:
        title = f"{BOLD}{title}{RESET}"
    label_width = max((len(label) for label, _ in fields), default=0)
    value_width = max(width() - label_width - 4, 20)
    lines = [f"  {title}", f"  {DIM}{'─' * rule}{RESET}" if colour else f"  {'─' * rule}"]
    for label, value in fields:
        pad = " " * (label_width - len(label))
        head = f"  {DIM}{label}{RESET}{pad}  " if colour else f"  {label}{pad}  "
        if len(value) <= value_width:
            lines.append(head + value)
            continue
        for offset, part in enumerate(wrap(value, value_width)):
            lines.append(head + part if offset == 0 else " " * (label_width + 4) + part)
    return lines


def render_table(records: list, columns: tuple | None, colour: bool) -> list[str]:
    if not records:
        return []
    columns = columns or tuple(label for label, _ in records[0]["fields"])
    fields = [ALIASES.get(label, label) for label in columns]
    rows = [[_string(dict(record["fields"]).get(field)) for field in fields]
            for record in records]
    widths = [max(len(label), *(len(row[i]) for row in rows))
              for i, label in enumerate(columns)]
    budget = width() - 2 * len(columns) - 1
    while sum(widths) > budget and max(widths) > 8:
        widths[widths.index(max(widths))] -= 1
    lines = []
    header = "  ".join(clip(label, widths[i]).ljust(widths[i]) for i, label in enumerate(columns))
    lines.append(f"{BOLD}{header}{RESET}" if colour else header)
    lines.append(f"{DIM}{'  '.join('─' * w for w in widths)}{RESET}" if colour
                 else "  ".join("─" * w for w in widths))
    for row in rows:
        cells = "  ".join(clip(value, widths[i]).ljust(widths[i]) for i, value in enumerate(row))
        lines.append(cells)
    return lines


def print_sections(sections: list, colour: bool, as_table: bool, source: str) -> None:
    out = []
    for index, group in enumerate(sections):
        records = group["records"]
        if not records:
            continue
        if index:
            out.append("")
        if group["title"] and not (len(records) == 1 and records[0]["title"] == group["title"]):
            out.append(f"{BOLD}{group['title']}{RESET}" if colour else group["title"])
        if as_table or group.get("columns"):
            out.extend(render_table(records, group.get("columns"), colour))
        else:
            longest = max([len(r["title"]) for r in records]
                          + [len(label) + 2 + len(_string(value))
                             for r in records for label, value in r["fields"]])
            for position, record in enumerate(records):
                if position:
                    out.append("")
                out.extend(render_card(record, colour, min(longest, width() - 2)))
    if not out:
        out.append(f"no results for {source!r}" if source else "no results")
    print("\n".join(out))


def flatten(items: list) -> tuple:
    """Columns for a spreadsheet, from (record, source) pairs. A column with no value in
    any record is dropped, so the export carries no wall of dashes the API did not fill."""
    labels: list[str] = ["Source"] if any(source for _, source in items) else []
    rows: list[dict] = []
    for record, source in items:
        row = {label: _string(value) for label, value in record["fields"]}
        for label in row:
            if label not in labels:
                labels.append(label)
        rows.append(dict(row, Source=source))
    filled = [label for label in labels
              if any(row.get(label, "-") not in ("", "-") for row in rows)]
    return filled, [{label: row.get(label, "") for label in filled} for row in rows]


def section_items(sections: list) -> list:
    return [(record, group.get("source", ""))
            for group in sections for record in group["records"]]


def to_json(sections: list) -> str:
    return json.dumps([group["raw"] for group in sections], indent=2, ensure_ascii=False)


def to_delimited(labels, rows, delimiter: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(labels)
    writer.writerows([[row.get(label, "") for label in labels] for row in rows])
    return buffer.getvalue()


def to_markdown(sections: list) -> str:
    blocks = []
    for group in sections:
        records = group["records"]
        if not records:
            continue
        labels, rows = flatten(section_items([group]))
        lines = [f"## {group['title']}" if group["title"] else "", "",
                 "| " + " | ".join(labels) + " |",
                 "|" + "|".join("---" for _ in labels) + "|"]
        lines += ["| " + " | ".join(row.get(label, "").replace("|", "\\|")
                                    for label in labels) + " |" for row in rows]
        blocks.append("\n".join(line for line in lines if line != "" or True))
    return "\n\n".join(blocks) + "\n" if blocks else "no results\n"


def to_html(sections: list) -> str:
    parts = ["<!doctype html>", '<html lang="id"><head><meta charset="utf-8">',
             "<title>PDDIKTI export</title>",
             "<style>body{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#111}"
             "table{border-collapse:collapse;width:100%;margin:0 0 2rem}"
             "th,td{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}"
             "th{background:#f2f2f2}</style></head><body>"]
    for group in sections:
        records = group["records"]
        if not records:
            continue
        labels, rows = flatten(section_items([group]))
        parts.append(f"<h2>{html.escape(group['title'])}</h2>" if group["title"] else "")
        parts.append("<table><thead><tr>"
                     + "".join(f"<th>{html.escape(label)}</th>" for label in labels)
                     + "</tr></thead><tbody>")
        for row in rows:
            parts.append("<tr>" + "".join(
                f"<td>{html.escape(row.get(label, ''))}</td>" for label in labels) + "</tr>")
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def write_export(sections: list, path: str, fmt: str) -> str:
    # An exported sheet nobody can trace back to its query is a sheet nobody trusts.
    labels, rows = flatten(section_items(sections))
    if fmt == "json":
        text = to_json(sections)
    elif fmt == "csv":
        text = to_delimited(labels, rows, ",")
    elif fmt == "tsv":
        text = to_delimited(labels, rows, "\t")
    elif fmt == "md":
        text = to_markdown(sections)
    elif fmt == "html":
        text = to_html(sections)
    else:
        raise ValueError(f"unknown format {fmt!r}")
    if path == "-":
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    return path
