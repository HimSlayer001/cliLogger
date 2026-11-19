"""Parse raw log lines into LogEntry objects."""

import re
from datetime import datetime

from logsleuth.models import LogEntry, LogLevel

# "2026-07-11 14:03:22 ERROR disk full"
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Za-z]+)\s+"
    r"(?P<message>.+?)\s*$"
)

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_line(line: str) -> LogEntry | None:
    """Parse one log line, returning None if it does not match the format."""
    raw = line.rstrip("\r\n")
    match = _LINE_RE.match(raw)
    if match is None:
        return None

    try:
        timestamp = datetime.strptime(match["ts"], _TIMESTAMP_FORMAT)
        level = LogLevel.from_string(match["level"])
    except ValueError:
        return None

    return LogEntry(
        timestamp=timestamp,
        level=level,
        message=match["message"],
        raw=raw,
    )
