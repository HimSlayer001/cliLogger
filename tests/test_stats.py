from datetime import datetime, timedelta
from pathlib import Path

import pytest

from logsleuth.io import LogReader
from logsleuth.models import LogEntry, LogLevel
from logsleuth.stats import (
    Burst,
    bucket_start,
    detect_bursts,
    errors_per_bucket,
    normalise_message,
    summarize,
)

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


MINUTE = timedelta(minutes=1)


def at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 7, 11, 12, minute, second)


def error_at(minute: int, second: int = 0) -> LogEntry:
    return make_entry("boom", LogLevel.ERROR, at(minute, second))


def test_bucket_start_floors_to_the_minute():
    assert bucket_start(at(7, 42), MINUTE) == at(7, 0)
    assert bucket_start(at(7, 0), MINUTE) == at(7, 0)


def test_bucket_start_other_sizes():
    assert bucket_start(at(7, 42), timedelta(minutes=5)) == at(5, 0)
    assert bucket_start(at(59, 59), timedelta(hours=1)) == at(0, 0)
    assert bucket_start(at(7, 42), timedelta(seconds=30)) == at(7, 30)


def test_bucket_start_rejects_non_positive():
    for bad in (timedelta(0), timedelta(minutes=-1)):
        with pytest.raises(ValueError):
            bucket_start(at(1), bad)


def test_errors_per_bucket_counts_only_errors():
    entries = [
        error_at(1, 5),
        error_at(1, 50),
        make_entry("fine", LogLevel.INFO, at(1, 30)),
        make_entry("warn", LogLevel.WARNING, at(1, 40)),
        make_entry("dead", LogLevel.CRITICAL, at(2, 10)),
    ]
    assert errors_per_bucket(entries) == {at(1): 2, at(2): 1}


def test_errors_per_bucket_fills_gaps_with_zero():
    histogram = errors_per_bucket([error_at(1), error_at(4)])
    assert histogram == {at(1): 1, at(2): 0, at(3): 0, at(4): 1}
    assert list(histogram) == sorted(histogram)


def test_errors_per_bucket_handles_unsorted_input():
    assert errors_per_bucket([error_at(3), error_at(1)]) == {
        at(1): 1,
        at(2): 0,
        at(3): 1,
    }


def test_errors_per_bucket_without_errors_is_empty():
    assert errors_per_bucket([]) == {}
    assert errors_per_bucket([make_entry("ok", LogLevel.INFO)]) == {}


def test_errors_per_bucket_custom_size():
    entries = [error_at(1), error_at(3), error_at(7)]
    assert errors_per_bucket(entries, timedelta(minutes=5)) == {at(0): 2, at(5): 1}


def test_errors_per_bucket_on_fixture():
    histogram = errors_per_bucket(LogReader(FIXTURE))
    assert histogram == {
        datetime(2026, 7, 11, 14, 3): 2,
        datetime(2026, 7, 11, 14, 4): 1,
    }


def histogram_of(*counts: int) -> dict[datetime, int]:
    return {at(minute): count for minute, count in enumerate(counts)}


def test_detect_bursts_finds_a_spike():
    bursts = detect_bursts(histogram_of(1, 0, 1, 12, 1, 0))
    assert bursts == (Burst(start=at(3), end=at(4), total=12, peak=12),)


def test_detect_bursts_merges_consecutive_hot_buckets():
    bursts = detect_bursts(histogram_of(0, 0, 0, 0, 9, 14, 0, 0, 0, 0, 0, 0))
    assert bursts == (Burst(start=at(4), end=at(6), total=23, peak=14),)


def test_detect_bursts_keeps_separate_spikes_apart():
    bursts = detect_bursts(histogram_of(0, 0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 10))
    assert [(b.start, b.end) for b in bursts] == [
        (at(5), at(6)),
        (at(11), at(12)),
    ]


def test_detect_bursts_flat_series_has_none():
    assert detect_bursts(histogram_of(4, 4, 4, 4, 4)) == ()


def test_detect_bursts_ignores_blips_below_min_count():
    assert detect_bursts(histogram_of(0, 0, 0, 0, 0, 0, 0, 0, 2)) == ()
    assert len(detect_bursts(histogram_of(0, 0, 0, 0, 0, 0, 0, 0, 2), min_count=2)) == 1


def test_detect_bursts_respects_bucket_size_for_end():
    five = timedelta(minutes=5)
    histogram = {at(0): 0, at(5): 0, at(10): 0, at(15): 0, at(20): 9}
    bursts = detect_bursts(histogram, five)
    assert bursts == (Burst(start=at(20), end=at(25), total=9, peak=9),)


def test_detect_bursts_empty_and_single_bucket():
    assert detect_bursts({}) == ()
    assert detect_bursts({at(0): 50}) == ()


def test_detect_bursts_validates_arguments():
    with pytest.raises(ValueError):
        detect_bursts(histogram_of(1), factor=0)
    with pytest.raises(ValueError):
        detect_bursts(histogram_of(1), min_count=0)
