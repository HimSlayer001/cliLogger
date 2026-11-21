"""Command-line interface: ``logsleuth summary`` and ``logsleuth filter``."""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta

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
from logsleuth.models import LogLevel
from logsleuth.parser import parse_timestamp
from logsleuth.stats import detect_bursts, errors_per_bucket, summarize

PROG = "logsleuth"


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


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with its subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROG, description="Inspect and summarise log files."
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    summary = commands.add_parser("summary", help="summarise a log file")
    summary.add_argument(
        "source", nargs="?", default=STDIN, help="log file, .gz file or '-' for stdin"
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

    filt = commands.add_parser("filter", help="print the entries that match")
    filt.add_argument(
        "source", nargs="?", default=STDIN, help="log file, .gz file or '-' for stdin"
    )
    filt.add_argument(
        "--level",
        type=str.lower,
        choices=[level.name.lower() for level in LogLevel],
        help="only entries at this level or more severe",
    )
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
    return parser


def _report_skipped(reader: LogReader) -> None:
    if reader.skipped:
        count = len(reader.skipped)
        print(f"{PROG}: skipped {count} unparseable line(s)", file=sys.stderr)


def _run_summary(args: argparse.Namespace) -> int:
    if args.top < 0:
        print(f"{PROG}: --top must be >= 0", file=sys.stderr)
        return 2
    if args.bucket < 1:
        print(f"{PROG}: --bucket must be >= 1", file=sys.stderr)
        return 2

    reader = LogReader(args.source)
    entries = list(reader)  # one read serves both the summary and the histogram
    result = summarize(entries, top_n=args.top)

    print(f"Entries: {result.total}")
    if result.first_timestamp and result.last_timestamp:
        print(f"Time range: {result.first_timestamp} to {result.last_timestamp}")
    print("Levels:")
    for level, count in result.by_level.items():
        print(f"  {level.name:<9}{count}")

    if result.top_messages:
        print("Top messages:")
        for message, count in result.top_messages:
            print(f"  {count:>5}  {message}")

    size = timedelta(seconds=args.bucket)
    bursts = detect_bursts(errors_per_bucket(entries, size), size)
    if bursts:
        print("Error bursts:")
        for burst in bursts:
            print(f"  {burst.start} to {burst.end}: {burst.total} errors")

    _report_skipped(reader)
    return 0


def _run_filter(args: argparse.Namespace) -> int:
    predicates: list[Predicate] = []
    if args.level:
        predicates.append(min_level(LogLevel[args.level.upper()]))
    if args.since:
        predicates.append(since(args.since))
    if args.until:
        predicates.append(until(args.until))
    predicates.extend(contains(text) for text in args.contains)
    predicates.extend(matches(pattern) for pattern in args.regex)

    reader = LogReader(args.source)
    for entry in apply_filters(reader, *predicates):
        print(entry.raw)

    _report_skipped(reader)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit status."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "summary":
            return _run_summary(args)
        return _run_filter(args)
    except FileNotFoundError as exc:
        print(f"{PROG}: no such file: {exc.filename}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0  # e.g. piped into `head`
