"""Parse raw log lines into LogEntry objects.

Several line layouts are recognised. Each one is a LogFormat in FORMATS and
is tried in order; the first whose pattern matches decides the result.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from logsleuth.models import LogEntry, LogLevel


class ParseError(ValueError):
    """Raised when a line cannot be turned into a LogEntry."""

    def __init__(self, line: str, reason: str) -> None:
        super().__init__(f"{reason}: {line!r}")
        self.line = line
        self.reason = reason


@dataclass(frozen=True, slots=True)
class LogFormat:
    """One recognised line layout: a name and a pattern with named groups."""

    name: str
    pattern: re.Pattern[str]


_TS = r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"

FORMATS: tuple[LogFormat, ...] = (
    # 2026-07-11 14:03:22 ERROR disk full
    # 2026-07-11T14:03:22.250Z ERROR disk full
    LogFormat(
        "plain",
        re.compile(rf"^(?P<ts>{_TS})\s+(?P<level>[A-Za-z]+)\s+(?P<message>.+?)\s*$"),
    ),
    # 2026-07-11 14:03:22 [ERROR] disk full
    # [2026-07-11T14:03:22Z] [ERROR] disk full
    LogFormat(
        "bracket",
        re.compile(
            rf"^\[?(?P<ts>{_TS})\]?\s+\[(?P<level>[A-Za-z]+)\]\s+(?P<message>.+?)\s*$"
        ),
    ),
)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-style timestamp; aware values are converted to naive UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def parse_line(line: str) -> LogEntry:
    """Parse one log line, raising ParseError if no format accepts it."""
    raw = line.rstrip("\r\n")
    if not raw.strip():
        raise ParseError(raw, "empty line")

    for log_format in FORMATS:
        match = log_format.pattern.match(raw)
        if match is None:
            continue
        try:
            timestamp = parse_timestamp(match["ts"])
        except ValueError as exc:
            raise ParseError(raw, "invalid timestamp") from exc
        try:
            level = LogLevel.from_string(match["level"])
        except ValueError as exc:
            raise ParseError(raw, "unknown log level") from exc
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=match["message"],
            raw=raw,
        )

    raise ParseError(raw, "unrecognised line format")


def try_parse_line(line: str) -> LogEntry | None:
    """Like parse_line, but return None instead of raising ParseError."""
    try:
        return parse_line(line)
    except ParseError:
        return None
