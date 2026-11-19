from datetime import datetime
from pathlib import Path

import pytest

from logsleuth.io import LogReader
from logsleuth.models import LogEntry, LogLevel
from logsleuth.stats import normalise_message, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "sample.log"


def make_entry(
    message: str = "x",
    level: LogLevel = LogLevel.INFO,
    timestamp: datetime = datetime(2026, 7, 11, 12, 0, 0),
) -> LogEntry:
    return LogEntry(timestamp=timestamp, level=level, message=message, raw=message)


def test_normalise_masks_digits():
    assert (
        normalise_message("connection to db-1 refused after 30s")
        == "connection to db-<N> refused after <N>s"
    )


def test_normalise_masks_prefixed_hex():
    assert normalise_message("request id=0x3fa9 done") == "request id=<HEX> done"


def test_normalise_masks_bare_hex_ids():
    assert normalise_message("session a4f19c02 closed") == "session <HEX> closed"


def test_normalise_leaves_plain_words_alone():
    assert normalise_message("defaced facade decade") == "defaced facade decade"


def test_normalise_groups_repeats():
    assert normalise_message("retry 1 of 5") == normalise_message("retry 4 of 5")


def test_summarize_empty():
    summary = summarize([])
    assert summary.total == 0
    assert summary.first_timestamp is None
    assert summary.last_timestamp is None
    assert summary.top_messages == ()
    assert summary.error_count == 0
    assert all(count == 0 for count in summary.by_level.values())


def test_summarize_counts_levels_in_severity_order():
    entries = [
        make_entry(level=LogLevel.ERROR),
        make_entry(level=LogLevel.INFO),
        make_entry(level=LogLevel.ERROR),
        make_entry(level=LogLevel.CRITICAL),
    ]
    summary = summarize(entries)
    assert summary.total == 4
    assert list(summary.by_level) == list(LogLevel)
    assert summary.by_level[LogLevel.ERROR] == 2
    assert summary.by_level[LogLevel.DEBUG] == 0
    assert summary.error_count == 3


def test_summarize_timestamps_ignore_line_order():
    entries = [
        make_entry(timestamp=datetime(2026, 7, 11, 12, 5)),
        make_entry(timestamp=datetime(2026, 7, 11, 12, 1)),
        make_entry(timestamp=datetime(2026, 7, 11, 12, 9)),
    ]
    summary = summarize(entries)
    assert summary.first_timestamp == datetime(2026, 7, 11, 12, 1)
    assert summary.last_timestamp == datetime(2026, 7, 11, 12, 9)


def test_summarize_top_messages_are_normalised_and_ranked():
    entries = [
        make_entry("retry 1"),
        make_entry("disk full"),
        make_entry("retry 2"),
        make_entry("retry 3"),
        make_entry("disk full"),
        make_entry("started"),
    ]
    summary = summarize(entries, top_n=2)
    assert summary.top_messages == (("retry <N>", 3), ("disk full", 2))


def test_summarize_ties_keep_first_seen_order():
    summary = summarize([make_entry("b"), make_entry("a")])
    assert summary.top_messages == (("b", 1), ("a", 1))


def test_summarize_top_n_zero_and_negative():
    assert summarize([make_entry()], top_n=0).top_messages == ()
    with pytest.raises(ValueError):
        summarize([], top_n=-1)


def test_summarize_accepts_a_generator():
    summary = summarize(make_entry(f"m{i}") for i in range(3))
    assert summary.total == 3


def test_summarize_sample_fixture():
    summary = summarize(LogReader(FIXTURE))
    assert summary.total == 7
    assert summary.by_level[LogLevel.ERROR] == 2
    assert summary.by_level[LogLevel.CRITICAL] == 1
    assert summary.first_timestamp == datetime(2026, 7, 11, 14, 3, 20)
    assert summary.last_timestamp == datetime(2026, 7, 11, 14, 4, 40)
    assert ("request id=<HEX> completed in <N>ms", 1) in summary.top_messages
