# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## 0.1.0 - 2026-11-22

First release.

### Added

- `logsleuth summary`: entry count, time range, per-level counts, most frequent
  messages, and bursts of errors.
- `logsleuth filter`: print matching lines by `--level`, `--since`, `--until`,
  and repeatable `--contains` and `--regex` conditions.
- `logsleuth top`: the most frequent messages, with numbers and hex ids masked
  so repeats group together.
- Log parsing for plain, ISO `T` and bracketed layouts, with fractional seconds
  and timezone offsets (converted to UTC). Unparseable lines are skipped and
  counted instead of stopping the run.
- Lazy streaming input from a file, a `.gz` archive or stdin.
- `--format text|json` on every command (one JSON object per line for
  `filter`) and `--color auto|always|never`, honouring `NO_COLOR`.
- Exit codes: 0 success, 1 unreadable input, 2 bad arguments, 130 interrupted.
- `python -m logsleuth` entry point and a small importable library (`parser`,
  `io`, `filters`, `stats`, `render`).
- README with usage and real sample output, `examples/burst.log`, strict mypy,
  and a test suite with 100% coverage and a 95% minimum.
- GitHub Actions workflow running ruff, mypy and pytest.
