"""Command-line interface: ``logsleuth summary``, ``filter`` and ``top``."""

import argparse
import gzip
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

from logsleuth.filters import (
    Predicate,
    apply_filters,
    contains,
    matches,
    min_level,
    since,
    until,
)
from logsleuth.io import STDIN, LogReader
from logsleuth.models import LogEntry, LogLevel
from logsleuth.parser import parse_timestamp
from logsleuth.render import BOLD, LEVEL_CODES, paint, use_color
from logsleuth.stats import detect_bursts, errors_per_bucket, summarize

PROG = "logsleuth"

EXIT_OK = 0
EXIT_ERROR = 1  # the input could not be read
EXIT_USAGE = 2  # bad arguments (also what argparse itself exits with)
EXIT_INTERRUPTED = 130  # Ctrl-C, by shell convention


def _timestamp(value: str) -> datetime:
    try:
        return parse_timestamp(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid timestamp {value!r} (use e.g. 2026-07-11T14:03:22)"
        ) from exc


def _regex(value: str) -> re.Pattern[str]:
    try:
        return re.compile(value)
    except re.error as exc:
        raise argparse.ArgumentTypeError(f"invalid regex {value!r}: {exc}") from exc


def _common_options() -> argparse.ArgumentParser:
    """Options shared by every subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "source", nargs="?", default=STDIN, help="log file, .gz file or '-' for stdin"
    )
    common.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    common.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour text output (default: auto; NO_COLOR disables auto)",
    )
    return common


def _add_level_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--level",
        type=str.lower,
        choices=[level.name.lower() for level in LogLevel],
        help="only entries at this level or more severe",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with its subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Inspect and summarise log files.",
        epilog="Exit status: 0 ok, 1 input could not be read, 2 bad arguments.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    common = _common_options()

    summary = commands.add_parser(
        "summary", parents=[common], help="summarise a log file"
    )
    summary.add_argument(
        "--top", type=int, default=5, metavar="N", help="most frequent messages to show"
    )
    summary.add_argument(
        "--bucket",
        type=int,
        default=60,
        metavar="SECONDS",
        help="bucket size for error burst detection (default: 60)",
    )

    filt = commands.add_parser(
        "filter",
        parents=[common],
        help="print the entries that match (JSON output is one object per line)",
    )
    _add_level_option(filt)
    filt.add_argument("--since", type=_timestamp, metavar="TIME", help="inclusive")
    filt.add_argument("--until", type=_timestamp, metavar="TIME", help="inclusive")
    filt.add_argument(
        "--contains",
        action="append",
        default=[],
        metavar="TEXT",
        help="message contains TEXT, ignoring case (repeatable)",
    )
    filt.add_argument(
        "--regex",
        action="append",
        default=[],
        type=_regex,
        metavar="PATTERN",
        help="message matches PATTERN (repeatable)",
    )

    top = commands.add_parser(
        "top", parents=[common], help="most frequent messages, numbers masked"
    )
    _add_level_option(top)
    top.add_argument(
        "-n", "--number", type=int, default=10, metavar="N", help="how many (default: 10)"
    )
    return parser


def _report_skipped(reader: LogReader) -> None:
    if reader.skipped:
        print(
            f"{PROG}: skipped {len(reader.skipped)} unparseable line(s)",
            file=sys.stderr,
        )


def _dump(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _entry_json(entry: LogEntry) -> dict[str, str]:
    return {
        "timestamp": entry.timestamp.isoformat(),
        "level": entry.level.name,
        "message": entry.message,
        "raw": entry.raw,
    }


def _run_summary(args: argparse.Namespace, color: bool) -> int:
    if args.top < 0:
        print(f"{PROG}: --top must be >= 0", file=sys.stderr)
        return EXIT_USAGE
    if args.bucket < 1:
        print(f"{PROG}: --bucket must be >= 1", file=sys.stderr)
        return EXIT_USAGE

    reader = LogReader(args.source)
    entries = list(reader)  # one read serves both the summary and the histogram
    result = summarize(entries, top_n=args.top)
    size = timedelta(seconds=args.bucket)
    bursts = detect_bursts(errors_per_bucket(entries, size), size)

    if args.format == "json":
        _dump(
            {
                "total": result.total,
                "first_timestamp": _iso(result.first_timestamp),
                "last_timestamp": _iso(result.last_timestamp),
                "levels": {level.name: n for level, n in result.by_level.items()},
                "top_messages": [
                    {"message": message, "count": count}
                    for message, count in result.top_messages
                ],
                "bursts": [
                    {
                        "start": burst.start.isoformat(),
                        "end": burst.end.isoformat(),
                        "total": burst.total,
                        "peak": burst.peak,
                    }
                    for burst in bursts
                ],
                "skipped": len(reader.skipped),
            }
        )
    else:

        def heading(text: str) -> str:
            return paint(text, BOLD, color)

        print(f"{heading('Entries:')} {result.total}")
        if result.first_timestamp and result.last_timestamp:
            print(
                f"{heading('Time range:')} "
                f"{result.first_timestamp} to {result.last_timestamp}"
            )
        print(heading("Levels:"))
        for level, count in result.by_level.items():
            name = paint(f"{level.name:<9}", LEVEL_CODES[level], color)
            print(f"  {name}{count}")
        if result.top_messages:
            print(heading("Top messages:"))
            for message, count in result.top_messages:
                print(f"  {count:>5}  {message}")
        if bursts:
            print(heading("Error bursts:"))
            for burst in bursts:
                print(f"  {burst.start} to {burst.end}: {burst.total} errors")

    _report_skipped(reader)
    return EXIT_OK


def _predicates(args: argparse.Namespace) -> list[Predicate]:
    predicates: list[Predicate] = []
    if args.level:
        predicates.append(min_level(LogLevel[args.level.upper()]))
    if getattr(args, "since", None):
        predicates.append(since(args.since))
    if getattr(args, "until", None):
        predicates.append(until(args.until))
    predicates.extend(contains(text) for text in getattr(args, "contains", []))
    predicates.extend(matches(pattern) for pattern in getattr(args, "regex", []))
    return predicates


def _run_filter(args: argparse.Namespace, color: bool) -> int:
    reader = LogReader(args.source)
    for entry in apply_filters(reader, *_predicates(args)):
        if args.format == "json":
            _dump(_entry_json(entry))
        else:
            print(paint(entry.raw, LEVEL_CODES[entry.level], color))
    _report_skipped(reader)
    return EXIT_OK


def _run_top(args: argparse.Namespace, color: bool) -> int:
    if args.number < 0:
        print(f"{PROG}: --number must be >= 0", file=sys.stderr)
        return EXIT_USAGE

    reader = LogReader(args.source)
    entries: Iterable[LogEntry] = apply_filters(reader, *_predicates(args))
    top = summarize(entries, top_n=args.number).top_messages

    if args.format == "json":
        _dump([{"message": message, "count": count} for message, count in top])
    else:
        for message, count in top:
            print(f"{paint(f'{count:>5}', BOLD, color)}  {message}")
    _report_skipped(reader)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit status."""
    args = build_parser().parse_args(argv)
    color = args.format == "text" and use_color(args.color, sys.stdout, os.environ)
    runners = {"summary": _run_summary, "filter": _run_filter, "top": _run_top}
    try:
        return runners[args.command](args, color)
    except BrokenPipeError:
        return EXIT_OK  # e.g. piped into `head`
    except FileNotFoundError as exc:
        print(f"{PROG}: no such file: {exc.filename}", file=sys.stderr)
        return EXIT_ERROR
    except (gzip.BadGzipFile, EOFError) as exc:
        print(f"{PROG}: corrupt gzip input: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        target = exc.filename or args.source
        print(f"{PROG}: cannot read {target}: {exc.strerror}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
