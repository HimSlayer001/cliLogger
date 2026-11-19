"""Summarise a stream of log entries."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from logsleuth.models import LogEntry, LogLevel

# 0x3fa9, or a bare hex id such as a4f19c02 (8+ chars, at least one digit so
# ordinary words like "defaced" are left alone).
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b|\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{8,}\b")
_DIGITS_RE = re.compile(r"\d+")


def normalise_message(message: str) -> str:
    """Mask the variable parts of a message so repeats group together.

    Hex values become <HEX> and every other run of digits becomes <N>:
    "connection to db-1 refused after 30s" -> "connection to db-<N> refused
    after <N>s".
    """
    return _DIGITS_RE.sub("<N>", _HEX_RE.sub("<HEX>", message))


@dataclass(frozen=True, slots=True)
class Summary:
    """Aggregate view of a set of log entries."""

    total: int
    by_level: Mapping[LogLevel, int]  # every level, in severity order
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    top_messages: tuple[tuple[str, int], ...]  # normalised message, count

    @property
    def error_count(self) -> int:
        """Entries at ERROR or CRITICAL."""
        return self.by_level[LogLevel.ERROR] + self.by_level[LogLevel.CRITICAL]


def summarize(entries: Iterable[LogEntry], top_n: int = 10) -> Summary:
    """Summarise entries in a single pass, so streams work as input.

    Ties in ``top_messages`` keep first-seen order. The first and last
    timestamps are the earliest and latest seen, whatever the line order.
    """
    if top_n < 0:
        raise ValueError("top_n must be >= 0")

    level_counts: Counter[LogLevel] = Counter()
    message_counts: Counter[str] = Counter()
    first: datetime | None = None
    last: datetime | None = None
    total = 0

    for entry in entries:
        total += 1
        level_counts[entry.level] += 1
        message_counts[normalise_message(entry.message)] += 1
        if first is None or entry.timestamp < first:
            first = entry.timestamp
        if last is None or entry.timestamp > last:
            last = entry.timestamp

    return Summary(
        total=total,
        by_level={level: level_counts[level] for level in LogLevel},
        first_timestamp=first,
        last_timestamp=last,
        top_messages=tuple(message_counts.most_common(top_n)),
    )
