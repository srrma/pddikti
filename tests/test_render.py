"""Self check for the output layer. Runs offline, no fixtures on disk."""

import io
import json
import sys
from contextlib import redirect_stdout

sys.path.insert(0, ".")

from pddikti import cli, render  # noqa: E402

FAILED = []


def check(name, got, want):
    if got != want:
        FAILED.append(f"{name}\n  got:  {got!r}\n  want: {want!r}")


check("number thousands", render.number(47128), "47,128")
check("number one decimal", render.number(73.6119), "73.6")
check("number zero", render.number(0), "0")
check("dash none", render.dash(None), "-")
check("dash empty", render.dash("   "), "-")
check("dash zero stays zero", render.dash(0), "0")
check("clip", render.clip("abcdefgh", 5), "abcd…")
check("clip noop", render.clip("abc", 5), "abc")
check("wrap keeps every word", render.wrap("a bb ccc dddd", 6), ["a bb", "ccc", "dddd"])
check("wrap short", render.wrap("a bb", 10), ["a bb"])
check("strip html", render.strip_html("<p>Ilmu</p>\n  <b>komputer</b>"), "Ilmu komputer")
check("strip html none", render.strip_html(None), "")
check("column alias", render.ALIASES["Prodi"], "Program studi")

check("ganjil semester", cli.current_semester(__import__("datetime").date(2026, 9, 30)), "20261")
check("genap semester", cli.current_semester(__import__("datetime").date(2026, 4, 1)), "20262")
check("december is ganjil", cli.current_semester(__import__("datetime").date(2026, 12, 1)), "20261")
check("january is ganjil", cli.current_semester(__import__("datetime").date(2027, 1, 5)), "20271")
check("previous semester", cli.previous_semester("20261"), "20252")

# A search hit must render its fields under their own labels, empty values as "-".
hit = {"nama_pt": "UNIVERSITAS GADJAH MADA", "kode_pt": "001001  ", "nama_singkat": "UGM",
       "provinsi_pt": "Prov. DI Yogyakarta", "kab_kota_pt": "Sleman",
       "akreditasi": "Unggul", "jumlah_prodi": 360}
record = render.pt_record(hit)
check("pt title", record["title"], "UNIVERSITAS GADJAH MADA")
check("pt name field", dict(record["fields"])["Nama"], "UNIVERSITAS GADJAH MADA")
check("pt kode stripped", dict(record["fields"])["Kode"], "001001  ")
check("pt jumlah_prodi", dict(record["fields"])["Program studi"], "360")
check("pt missing is dash", render._string(record["fields"][-1][1]), "-")

# The card shows the name once: as the bold title, never again as a field.
card_fields = [line for line in render.render_card(record, colour=False, rule=10)
               if "GADJAH MADA" in line]
check("name appears once", len(card_fields), 1)

# The table must fit the terminal: shrinking a column shortens the whole line.
records = [render.pt_record(hit), render.pt_record({**hit, "nama_pt": "X" * 90, "kode_pt": "002002"})]
table = render.render_table(records, render.SEARCH_COLUMNS["pt"], colour=False)
check("table header", table[0].split()[0], "Nama")
check("table has every row", len(table), 4)
check("table fits width", all(len(line) <= render.width() for line in table), True)

# Colour is a flag, not a constant: the same text has to come out clean without it.
card = render.render_card(record, colour=False, rule=10)
check("card no escapes", any("\033" in line for line in card), False)
check("card with escapes", any("\033" in line for line in render.render_card(record, True, 10)), True)

# Prose wraps instead of being cut off, and keeps the continuation under the value.
long_record = {"title": "t", "fields": [("Deskripsi", " ".join(["kata"] * 60))]}
wrapped = render.render_card(long_record, colour=False, rule=4)
check("card wraps", len(wrapped) > 4, True)
check("wrap keeps the end", wrapped[-1].split()[-1], "kata")
check("wrap indents", all(line.startswith("  Deskripsi") or line.startswith("    ")
                          for line in wrapped[2:]), True)

# A list value becomes one cell rather than a Python repr.
check("list flattens", render._string([{"nama": "A"}, {"nama": "B"}]), "A; B")

sections = [render.section("t", [record], hit, render.SEARCH_COLUMNS["pt"], "gadjah")]
labels, rows = render.flatten(render.section_items(sections))
check("flatten labels", labels[1], "Nama")
check("flatten rows", rows[0]["Nama"], "UNIVERSITAS GADJAH MADA")
check("json keeps upstream", json.loads(render.to_json(sections))[0]["kode_pt"], "001001  ")
check("csv header", render.to_delimited(labels, rows, ",").splitlines()[0].split(",")[1], "Nama")
check("md pipes", render.to_markdown(sections).count("|"), 3 * (len(labels) + 1))
check("source column kept", "Source" in labels, True)
check("source value", rows[0]["Source"], "gadjah")
check("empty column dropped", "Pembina" in labels, False)
check("section_items pairs", render.section_items(sections)[0][1], "gadjah")
check("html escapes", "&" in render.to_html(
    [render.section("a&b", [render.pt_record(hit)], hit)]), True)

# No export format may be accepted that cannot be written.
check("formats", sorted(render.EXPORT_FORMATS),
      ["csv", "html", "json", "md", "tsv"])
check("format from extension", cli.export_format("out.csv", None), "csv")
check("format override", cli.export_format("out.csv", "json"), "json")
check("unknown extension ignored", cli.export_format("out.xlsx", None), None)
check("stdout has no format", cli.export_format("-", None), None)

# A term file keeps order and drops blanks, comments and duplicates.
import tempfile  # noqa: E402
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
    handle.write("# comment\n\ngadjah\nitb\nGADJAH\n")
    path = handle.name
args = cli.build_parser().parse_args(["pt", "--file", path])
check("terms from file", cli.collect_terms(args), ["gadjah", "itb", "GADJAH"])

# An empty result set must say so rather than print nothing at all.
buffer = io.StringIO()
with redirect_stdout(buffer):
    render.print_sections([], colour=False, as_table=False, source="zzz")
check("empty state", buffer.getvalue().strip(), "no results for 'zzz'")

if FAILED:
    print("\n".join(FAILED))
    raise SystemExit(f"{len(FAILED)} check(s) failed")
print("all checks passed")
