"""Composable predicates for selecting log entries.

Each builder returns a Predicate, a function from LogEntry to bool. Combine
them with all_of, any_of and negate, and run them over a stream with
apply_filters.
"""

import re
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime

from logsleuth.models import LogEntry, LogLevel

Predicate = Callable[[LogEntry], bool]

# LogLevel is declared least to most severe, so definition order is the rank.
_SEVERITY: dict[LogLevel, int] = {level: rank for rank, level in enumerate(LogLevel)}


def min_level(level: LogLevel) -> Predicate:
    """Match entries at ``level`` or more severe."""
    threshold = _SEVERITY[level]
    return lambda entry: _SEVERITY[entry.level] >= threshold


def since(start: datetime) -> Predicate:
    """Match entries at or after ``start`` (inclusive)."""
    return lambda entry: entry.timestamp >= start


def until(end: datetime) -> Predicate:
    """Match entries at or before ``end`` (inclusive)."""
    return lambda entry: entry.timestamp <= end


def contains(text: str, *, case_sensitive: bool = False) -> Predicate:
    """Match entries whose message contains ``text``."""
    if case_sensitive:
        return lambda entry: text in entry.message
    needle = text.casefold()
    return lambda entry: needle in entry.message.casefold()


def matches(pattern: str | re.Pattern[str], flags: int = 0) -> Predicate:
    """Match entries whose message has a regex match anywhere in it.

    An invalid pattern raises re.error here, not when the filter first runs.
    """
    compiled = re.compile(pattern, flags)
    return lambda entry: compiled.search(entry.message) is not None


def all_of(*predicates: Predicate) -> Predicate:
    """Match when every predicate matches (always true with none)."""
    return lambda entry: all(predicate(entry) for predicate in predicates)


def any_of(*predicates: Predicate) -> Predicate:
    """Match when at least one predicate matches (never true with none)."""
    return lambda entry: any(predicate(entry) for predicate in predicates)


def negate(predicate: Predicate) -> Predicate:
    """Match exactly the entries the predicate does not."""
    return lambda entry: not predicate(entry)


def apply_filters(
    entries: Iterable[LogEntry], *predicates: Predicate
) -> Iterator[LogEntry]:
    """Lazily yield the entries that satisfy every predicate."""
    combined = all_of(*predicates)
    return (entry for entry in entries if combined(entry))
