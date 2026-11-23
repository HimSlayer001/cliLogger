"""Summarise a stream of log entries."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

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


_EPOCH = datetime(1970, 1, 1)


def bucket_start(timestamp: datetime, bucket: timedelta) -> datetime:
    """Round a timestamp down to the start of its bucket.

    Buckets are aligned to the Unix epoch, so one-minute buckets start on
    the minute and one-hour buckets on the hour.
    """
    if bucket <= timedelta(0):
        raise ValueError("bucket must be a positive duration")
    return _EPOCH + ((timestamp - _EPOCH) // bucket) * bucket


def errors_per_bucket(
    entries: Iterable[LogEntry], bucket: timedelta = timedelta(minutes=1)
) -> dict[datetime, int]:
    """Count ERROR and CRITICAL entries in each time bucket.

    The result is sorted by time and contiguous: buckets with no errors
    between the first and last error are included with a count of 0, so the
    histogram can be drawn or scanned without gaps. No errors gives {}.
    """
    counts: Counter[datetime] = Counter()
    for entry in entries:
        if entry.is_error():
            counts[bucket_start(entry.timestamp, bucket)] += 1
    if not counts:
        return {}

    histogram: dict[datetime, int] = {}
    current, last = min(counts), max(counts)
    while current <= last:
        histogram[current] = counts.get(current, 0)
        current += bucket
    return histogram


@dataclass(frozen=True, slots=True)
class Burst:
    """A run of consecutive buckets with unusually many errors."""

    start: datetime  # start of the first bucket
    end: datetime  # end of the last bucket (exclusive)
    total: int  # errors across the run
    peak: int  # errors in the busiest bucket


def detect_bursts(
    histogram: Mapping[datetime, int],
    bucket: timedelta = timedelta(minutes=1),
    *,
    factor: float = 3.0,
    min_count: int = 3,
) -> tuple[Burst, ...]:
    """Find spikes in an errors_per_bucket histogram.

    A bucket is hot when it holds at least ``min_count`` errors and at least
    ``factor`` times the mean bucket count. Consecutive hot buckets merge
    into one Burst. A flat series, or a single bucket, has no bursts.
    """
    if factor <= 0:
        raise ValueError("factor must be > 0")
    if min_count < 1:
        raise ValueError("min_count must be >= 1")
    if not histogram:
        return ()

    threshold = max(min_count, factor * (sum(histogram.values()) / len(histogram)))

    bursts: list[Burst] = []
    run: list[tuple[datetime, int]] = []

    def close_run() -> None:
        if run:
            counts = [count for _, count in run]
            bursts.append(
                Burst(
                    start=run[0][0],
                    end=run[-1][0] + bucket,
                    total=sum(counts),
                    peak=max(counts),
                )
            )
            run.clear()

    for start in sorted(histogram):
        count = histogram[start]
        if count >= threshold and (not run or start == run[-1][0] + bucket):
            run.append((start, count))
        elif count >= threshold:
            close_run()
            run.append((start, count))
        else:
            close_run()
    close_run()
    return tuple(bursts)
