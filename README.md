# logsleuth

A small command-line tool for making sense of log files. Point it at a file, a
`.gz` archive or stdin and it will summarise what happened, filter the lines
you care about, or show which messages repeat the most, even when the repeats
differ only by a number or an id.

```console
$ logsleuth summary examples/burst.log --top 2
Entries: 18
Time range: 2026-07-11 10:01:00 to 2026-07-11 10:09:00
Levels:
  DEBUG    0
  INFO     1
  WARNING  0
  ERROR    17
  CRITICAL 0
Top messages:
     10  connection to db-<N> refused
      7  upstream timeout after <N>s
Error bursts:
  2026-07-11 10:08:00 to 2026-07-11 10:09:00: 10 errors
```

## Install

logsleuth needs Python 3.14 or newer and is not published to PyPI, so install
it from a clone. With [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/HimSlayer001/cliLogger.git
cd cliLogger
uv sync
uv run logsleuth --help
```

To put `logsleuth` on your `PATH`, run `uv tool install .` from the clone.
`python -m logsleuth` works too.

## Usage

Every command takes a file path, a `.gz` file, or `-` for stdin (the default
when no path is given), so it works in a pipe:

```sh
zcat app.log.gz | logsleuth summary
kubectl logs my-pod | logsleuth filter --level warning
```

### `summary`

Entry count, time range, a count per level, the most frequent messages, and any
bursts of errors.

```console
$ logsleuth summary tests/fixtures/sample.log
Entries: 7
Time range: 2026-07-11 14:03:20 to 2026-07-11 14:04:40
Levels:
  DEBUG    1
  INFO     2
  WARNING  1
  ERROR    2
  CRITICAL 1
Top messages:
      1  service started on port <N>
      1  loaded <N> routes
      1  disk full on /dev/sda<N>
      1  retrying connection to db-<N> (attempt <N>)
      1  connection to db-<N> refused
```

| Option | Meaning |
| --- | --- |
| `--top N` | How many frequent messages to list (default 5) |
| `--bucket SECONDS` | Bucket size used to look for error bursts (default 60) |

A **burst** is a run of buckets where the error count is at least three times
the average bucket and at least three errors. Bursts are measured against the
other error buckets in the same file, so a file whose errors all land in one
bucket has nothing to compare against and reports none.

### `filter`

Prints the matching lines exactly as they appear in the log. All conditions
must match.

```console
$ logsleuth filter tests/fixtures/sample.log --level error
2026-07-11 14:03:22 ERROR disk full on /dev/sda1
2026-07-11 14:03:31 ERROR connection to db-1 refused
2026-07-11 14:04:40 CRITICAL out of memory, shutting down

$ logsleuth filter tests/fixtures/sample.log --contains db --since 2026-07-11T14:03:25
2026-07-11 14:03:25 WARNING retrying connection to db-1 (attempt 2)
2026-07-11 14:03:31 ERROR connection to db-1 refused
```

| Option | Meaning |
| --- | --- |
| `--level LEVEL` | This level or more severe: `debug`, `info`, `warning`, `error`, `critical` |
| `--since TIME` | At or after this time (inclusive) |
| `--until TIME` | At or before this time (inclusive) |
| `--contains TEXT` | Message contains TEXT, ignoring case. Repeatable |
| `--regex PATTERN` | Message matches the regular expression. Repeatable |

Times are ISO-style, with or without a timezone: `2026-07-11T14:03:22`,
`2026-07-11 14:03:22` or `2026-07-11T19:33:22+05:30`.

### `top`

The most frequent messages, with numbers and hex ids masked so that
`retry 1` and `retry 4` count as the same thing.

```console
$ logsleuth top tests/fixtures/sample.log -n 3
    1  service started on port <N>
    1  loaded <N> routes
    1  disk full on /dev/sda<N>
```

Use `-n N` for how many (default 10) and `--level` to look at errors only.

### Output formats and colour

All commands accept:

- `--format text|json`. `filter` prints one JSON object per line, ready for
  `jq`. `summary` and `top` print a single JSON document.
- `--color auto|always|never`. The default, `auto`, colours only a terminal,
  and `NO_COLOR` or `TERM=dumb` turns it off. JSON is never coloured.

```console
$ logsleuth filter tests/fixtures/sample.log --level critical --format json
{"timestamp": "2026-07-11T14:04:40", "level": "CRITICAL", "message": "out of memory, shutting down", "raw": "2026-07-11 14:04:40 CRITICAL out of memory, shutting down"}
```

### Exit status

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | The input could not be read (missing file, a directory, corrupt gzip) |
| 2 | Bad arguments |
| 130 | Interrupted with Ctrl-C |

Lines that cannot be parsed are skipped, not treated as errors. A count is
printed to stderr: `logsleuth: skipped 3 unparseable line(s)`.

## Log formats

Each entry is one line with a timestamp, a level and a message. These layouts
are recognised:

```text
2026-07-11 14:03:22 ERROR disk full
2026-07-11T14:03:22.250Z ERROR disk full
2026-07-11 14:03:22 [ERROR] disk full
[2026-07-11T14:03:22Z] [error] disk full
```

Levels are case-insensitive. Timestamps with a timezone are converted to UTC,
and timestamps without one are used as written, so don't mix the two in a
single comparison. Blank lines are ignored. A message that spans several lines,
such as a stack trace, counts its continuation lines as unparseable.

## Use it as a library

The pieces behind the commands are plain Python:

```python
from logsleuth.filters import apply_filters, min_level
from logsleuth.io import LogReader
from logsleuth.models import LogLevel
from logsleuth.stats import summarize

reader = LogReader("examples/burst.log")
errors = apply_filters(reader, min_level(LogLevel.ERROR))
print(summarize(errors, top_n=1).top_messages)
# (('connection to db-<N> refused', 10),)
print(len(reader.skipped))  # 0, lines that could not be parsed
```

| Module | What it does |
| --- | --- |
| `parser` | Turns a line into a `LogEntry`, or raises `ParseError`. New layouts are one entry in `FORMATS` |
| `io` | `LogReader` streams entries lazily from a path, `.gz` or stdin and records skipped lines |
| `filters` | Composable predicates: `min_level`, `since`, `until`, `contains`, `matches`, `all_of`, `any_of`, `negate` |
| `stats` | `summarize`, `errors_per_bucket` and `detect_bursts` |
| `render` | Terminal colour helpers |
| `cli` | The argparse interface |

## Development

```sh
uv sync
uv run pytest
uv run ruff check
uv run mypy src
```

Tests live in `tests/`, with a sample log in `tests/fixtures/sample.log`.
`examples/burst.log` is a larger sample with a burst of database errors.
