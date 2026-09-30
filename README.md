# pddikti

Query PDDIKTI, the Indonesian higher-education registry, from the terminal.

PDDIKTI is run by Direktorat Jenderal Pendidikan Tinggi, Kemendiktisaintek. This tool is a
client for the same JSON API the pddikti.kemdiktisaintek.go.id website uses. It has no
runtime dependencies, no API key, and no configuration file.

## Install

```bash
uv tool install ~/Developer/pddikti      # or: pipx install ~/Developer/pddikti
```

Or run it in place, which is enough for trying it out:

```bash
cd ~/Developer/pddikti && python3 -m pddikti --help
```

Python 3.11 or newer.

## Commands

```
pddikti pt <term>...       search universities
pddikti prodi <term>...    search study programs
pddikti mhs <term>...      search students
pddikti dosen <term>...    search lecturers
pddikti all <term>...      search all four at once
pddikti stats              national totals and the field-of-study breakdown
```

Add `-d` to expand a hit in full, and `--match N` to pick which one.

```bash
pddikti pt gadjah
pddikti pt gadjah -d
pddikti pt gadjah -d --prodi                     # plus every study program
pddikti pt gadjah --logo ugm.png

pddikti prodi "ilmu komputer"
pddikti prodi "hukum" --pt gadjah                # scoped to one university
pddikti prodi "hukum" --pt gadjah -d --dosen     # plus its homebase lecturers

pddikti mhs "andi abdi" -d
pddikti mhs --nim 01151385EHK00274

pddikti dosen "budi santoso" -d                  # profile, education, subjects, portfolios
```

## Filtering universities

`pt` is the only command with facets. `provinsi` needs PDDIKTI's exact wording, for example
`Prov. Jawa Barat`. A filter that matches nothing prints a hint, because the server matches
these labels literally.

```bash
pddikti pt "" --provinsi "Prov. Jawa Barat" --akreditasi Unggul --jenis PTN
pddikti pt "" --akreditasi Unggul --all-pages --limit 100 -o excell.xlsx.csv
```

`--limit` is per page, up to 100. `--all-pages` walks every page instead of the first.

## Bulk queries

Any command takes any number of terms, and terms can come from a file or standard input.

```bash
pddikti pt gadjah itb ugm                       # three searches, one command
pddikti pt --file daftar.txt                    # one term per line, # comments allowed
cut -d, -f2 daftar.csv | pddikti pt --stdin     # straight out of a pipeline
pddikti prodi --file prodi.txt --jobs 8 -o hasil.csv
pddikti pt --file daftar.txt --count            # one count per term, for scripts
```

`--jobs N` caps concurrent requests and defaults to 4. `--delay SEC` pauses before each
request, which is worth using for a long run against a public government service. A term
that fails prints one `!` line and the rest of the run continues.

## Export

`-o FILE` picks the format from the extension, `--format` overrides it, and `-o -` writes to
standard output.

| Format | Extension | Opens in |
|---|---|---|
| JSON | `.json` | anything, lossless upstream shape |
| CSV | `.csv` | Excel, Sheets, pandas, R |
| TSV | `.tsv` | CSV when values contain commas |
| Markdown | `.md` | reports, pull requests, notes |
| HTML | `.html` | Excel and Sheets, as a real table |

Every row carries a `Source` column with the term that produced it. Columns that came back
empty for every record are left out, so a spreadsheet is not mostly dashes.

## Reading the output

Results are a table. `-d` is a record card with the name in bold, the labels dimmed, and a
rule sized to the record. Prose such as a study-program description wraps instead of being cut
off. Numbers get thousands separators. A value PDDIKTI does not have shows as `-`.

`NO_COLOR` and a redirected standard output turn colour off on their own. `--json` prints the
upstream JSON untouched, so `pddikti pt gadjah --json | jq` works.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | ran, at least one record |
| 1 | ran, nothing found, or a term failed |
| 2 | usage error |
| 3 | every term failed on the network |

## Environment

| Variable | Default |
|---|---|
| `PDDIKTI_BASE_URL` | `https://pddikti.kemdiktisaintek.go.id/api` |
| `PDDIKTI_TIMEOUT` | `30` seconds |
| `PDDIKTI_JOBS` | `4` |
| `NO_COLOR` | unset |

## Tests

```bash
python3 tests/test_render.py
```

Runs offline, no network and no fixtures on disk. It covers formatting, the semester
calculation, colour gating, and every export writer.

The live API is verified endpoint by endpoint by hand, not by this test. Some endpoints on
the server return nothing useful or are dead, and those are deliberately not exposed.

## Notes

The old `api-frontend.kemdikbud.go.id` API is gone. `kemdikbud.go.id` no longer resolves at
all, and every public mirror built on it is down. The API moved with the ministry to
`pddikti.kemdiktisaintek.go.id`.

The server answers `403` to clients that do not look like the website's own XHR. Sending a
browser user agent together with an `Origin` header is all it takes. That is bot detection,
not authentication, and it is why this tool has no key to configure.

The API is undocumented, so a deploy on the government side can break it without warning.
`PDDIKTI_BASE_URL` moves the tool to a new host, and an issue with the failing path and the
status it returned is the most useful report anyone can file.
