import re
from datetime import datetime
from pathlib import Path

import pytest

from logsleuth.filters import (
    all_of,
    any_of,
    apply_filters,
    contains,
    matches,
    min_level,
    negate,
    since,
    until,
)
from logsleuth.io import LogReader
from logsleuth.models import LogEntry, LogLevel

FIXTURE = Path(__file__).parent / "fixtures" / "sample.log"


def make_entry(
    message: str = "x",
    level: LogLevel = LogLevel.INFO,
    timestamp: datetime = datetime(2026, 7, 11, 12, 0, 0),
) -> LogEntry:
    return LogEntry(timestamp=timestamp, level=level, message=message, raw=message)


def test_min_level_includes_threshold_and_above():
    predicate = min_level(LogLevel.WARNING)
    assert not predicate(make_entry(level=LogLevel.DEBUG))
    assert not predicate(make_entry(level=LogLevel.INFO))
    assert predicate(make_entry(level=LogLevel.WARNING))
    assert predicate(make_entry(level=LogLevel.ERROR))
    assert predicate(make_entry(level=LogLevel.CRITICAL))


def test_min_level_debug_matches_everything():
    predicate = min_level(LogLevel.DEBUG)
    assert all(predicate(make_entry(level=level)) for level in LogLevel)


def test_since_is_inclusive():
    boundary = datetime(2026, 7, 11, 12, 0, 0)
    predicate = since(boundary)
    assert predicate(make_entry(timestamp=boundary))
    assert predicate(make_entry(timestamp=datetime(2026, 7, 11, 12, 0, 1)))
    assert not predicate(make_entry(timestamp=datetime(2026, 7, 11, 11, 59, 59)))


def test_until_is_inclusive():
    boundary = datetime(2026, 7, 11, 12, 0, 0)
    predicate = until(boundary)
    assert predicate(make_entry(timestamp=boundary))
    assert predicate(make_entry(timestamp=datetime(2026, 7, 11, 11, 59, 59)))
    assert not predicate(make_entry(timestamp=datetime(2026, 7, 11, 12, 0, 1)))


def test_contains_is_case_insensitive_by_default():
    predicate = contains("DISK")
    assert predicate(make_entry("disk full"))
    assert not predicate(make_entry("network down"))


def test_contains_case_sensitive():
    predicate = contains("DISK", case_sensitive=True)
    assert predicate(make_entry("DISK full"))
    assert not predicate(make_entry("disk full"))


def test_contains_only_looks_at_the_message():
    entry = LogEntry(
        timestamp=datetime(2026, 7, 11),
        level=LogLevel.INFO,
        message="ok",
        raw="2026-07-11 INFO ok secret",
    )
    assert not contains("secret")(entry)


def test_matches_searches_anywhere():
    predicate = matches(r"db-\d+")
    assert predicate(make_entry("connection to db-1 refused"))
    assert not predicate(make_entry("connection refused"))


def test_matches_accepts_flags_and_compiled_patterns():
    assert matches("DISK", re.IGNORECASE)(make_entry("disk full"))
    assert matches(re.compile("full$"))(make_entry("disk full"))


def test_matches_rejects_invalid_pattern_immediately():
    with pytest.raises(re.error):
        matches("(unclosed")


def test_all_of_requires_every_predicate():
    predicate = all_of(min_level(LogLevel.ERROR), contains("disk"))
    assert predicate(make_entry("disk full", LogLevel.ERROR))
    assert not predicate(make_entry("disk full", LogLevel.INFO))
    assert not predicate(make_entry("net down", LogLevel.ERROR))


def test_all_of_empty_matches_everything():
    assert all_of()(make_entry())


def test_any_of_needs_one_predicate():
    predicate = any_of(contains("disk"), contains("memory"))
    assert predicate(make_entry("out of memory"))
    assert predicate(make_entry("disk full"))
    assert not predicate(make_entry("net down"))


def test_any_of_empty_matches_nothing():
    assert not any_of()(make_entry())


def test_negate_inverts():
    predicate = negate(contains("debug"))
    assert predicate(make_entry("ok"))
    assert not predicate(make_entry("debug info"))


def test_predicates_compose_into_a_time_window():
    window = all_of(
        since(datetime(2026, 7, 11, 14, 3, 21)),
        until(datetime(2026, 7, 11, 14, 4, 2)),
    )
    messages = [e.message for e in apply_filters(LogReader(FIXTURE), window)]
    assert len(messages) == 5
    assert messages[0] == "loaded 42 routes"


def test_apply_filters_is_lazy():
    def source():
        yield make_entry("first")
        raise AssertionError("consumed past what was requested")

    iterator = apply_filters(source(), contains("first"))
    assert next(iterator).message == "first"


def test_apply_filters_with_no_predicates_passes_everything():
    entries = [make_entry("a"), make_entry("b")]
    assert list(apply_filters(entries)) == entries


def test_apply_filters_on_fixture_errors_only():
    errors = list(apply_filters(LogReader(FIXTURE), min_level(LogLevel.ERROR)))
    assert [e.level for e in errors] == [
        LogLevel.ERROR,
        LogLevel.ERROR,
        LogLevel.CRITICAL,
    ]
