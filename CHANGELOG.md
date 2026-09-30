# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0, 2026-09-30

First release.

### Added

- `pt`, `prodi`, `mhs`, `dosen`, `all` and `stats` commands over the live PDDIKTI API.
- `-d` to expand a hit: full university profile, study-program profile with its
  description, per-semester student and lecturer series, student record, and lecturer
  record with education history, subjects taught and all four portfolios.
- `pt -d --prodi` lists every study program of a university for the semester, and
  `prodi -d --dosen` lists a program's homebase lecturers.
- `pt --logo PATH` downloads a university logo.
- `pt` facets on province, accreditation and institution type, with real pagination
  and `--all-pages`.
- `prodi --pt NAME` searches inside one university.
- `mhs --nim` resolves a student by NIM.
- Bulk queries: many terms at once, `--file`, `--stdin`, `--jobs`, `--delay`, `--count`.
- Export to JSON, CSV, TSV, Markdown and HTML, with a `Source` column on every row and
  empty columns dropped.
- `--json` for the untouched upstream payload, `--table` to force a table,
  `NO_COLOR` honoured.
- `PDDIKTI_BASE_URL`, `PDDIKTI_TIMEOUT` and `PDDIKTI_JOBS`.

### Notes

- No API key. The server gates on bot detection, not authentication, and the client
  satisfies it with a browser user agent and an `Origin` header.
- Entity identifiers are opaque and change on every response, so the tool resolves them
  for you and never asks you to pass one.
- The API is undocumented and can move or change without notice. Three endpoints are
  already dead on the server and are not exposed.
