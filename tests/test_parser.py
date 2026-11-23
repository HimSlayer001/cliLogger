from datetime import datetime
from pathlib import Path

from logsleuth.models import LogLevel
import pytest

from logsleuth.parser import ParseError, parse_line, try_parse_line

FIXTURE = Path(__file__).parent / "fixtures" / "sample.log"


def test_parse_line_basic():
    entry = parse_line("2026-07-11 14:03:22 ERROR disk full")
    assert entry.timestamp == datetime(2026, 7, 11, 14, 3, 22)
    assert entry.level is LogLevel.ERROR
    assert entry.message == "disk full"


def test_parse_line_keeps_raw_without_newline():
    line = "2026-07-11 14:03:22 INFO started\n"
    entry = parse_line(line)
    assert entry.raw == "2026-07-11 14:03:22 INFO started"


def test_parse_line_level_is_case_insensitive():
    entry = parse_line("2026-07-11 14:03:22 warning low disk")
    assert entry.level is LogLevel.WARNING


def test_parse_line_message_keeps_inner_spacing():
    entry = parse_line("2026-07-11 14:03:22 INFO a  b   c")
    assert entry.message == "a  b   c"


def test_parse_line_rejects_garbage():
    with pytest.raises(ParseError, match="unrecognised line format"):
        parse_line("not a log line")


def test_parse_line_rejects_empty_and_blank_lines():
    for line in ("", "   ", "\n"):
        with pytest.raises(ParseError, match="empty line"):
            parse_line(line)


def test_parse_line_rejects_unknown_level():
    with pytest.raises(ParseError, match="unknown log level"):
        parse_line("2026-07-11 14:03:22 LOUD something")


def test_parse_line_rejects_impossible_date():
    with pytest.raises(ParseError, match="invalid timestamp"):
        parse_line("2026-13-45 14:03:22 INFO x")


def test_parse_line_rejects_missing_message():
    with pytest.raises(ParseError):
        parse_line("2026-07-11 14:03:22 ERROR")


def test_parse_error_carries_line_and_reason():
    with pytest.raises(ParseError) as info:
        parse_line("garbage\n")
    assert info.value.line == "garbage"
    assert info.value.reason == "unrecognised line format"
    assert "garbage" in str(info.value)


def test_parse_line_accepts_iso_t_separator():
    entry = parse_line("2026-07-11T14:03:22 INFO started")
    assert entry.timestamp == datetime(2026, 7, 11, 14, 3, 22)


def test_parse_line_accepts_fractional_seconds():
    entry = parse_line("2026-07-11T14:03:22.250 INFO started")
    assert entry.timestamp == datetime(2026, 7, 11, 14, 3, 22, 250000)


def test_parse_line_converts_aware_timestamps_to_naive_utc():
    z = parse_line("2026-07-11T14:03:22Z INFO a")
    offset = parse_line("2026-07-11T19:33:22+05:30 INFO a")
    assert z.timestamp == datetime(2026, 7, 11, 14, 3, 22)
    assert offset.timestamp == z.timestamp
    assert z.timestamp.tzinfo is None


def test_parse_line_bracket_level_style():
    entry = parse_line("2026-07-11 14:03:22 [ERROR] disk full")
    assert entry.level is LogLevel.ERROR
    assert entry.message == "disk full"


def test_parse_line_fully_bracketed_style():
    entry = parse_line("[2026-07-11T14:03:22Z] [warning] low disk")
    assert entry.level is LogLevel.WARNING
    assert entry.timestamp == datetime(2026, 7, 11, 14, 3, 22)
    assert entry.message == "low disk"


def test_try_parse_line_returns_none_on_failure():
    assert try_parse_line("not a log line") is None
    assert try_parse_line("") is None


def test_try_parse_line_returns_entry_on_success():
    entry = try_parse_line("2026-07-11 14:03:22 INFO ok")
    assert entry is not None
    assert entry.message == "ok"


def test_sample_fixture_parses_fully():
    lines = FIXTURE.read_text().splitlines()
    entries = [parse_line(line) for line in lines]
    assert [e.level for e in entries][:3] == [
        LogLevel.INFO,
        LogLevel.DEBUG,
        LogLevel.ERROR,
    ]
    assert len(entries) == 7
