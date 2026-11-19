from datetime import datetime
from pathlib import Path

from logsleuth.models import LogLevel
from logsleuth.parser import parse_line

FIXTURE = Path(__file__).parent / "fixtures" / "sample.log"


def test_parse_line_basic():
    entry = parse_line("2026-07-11 14:03:22 ERROR disk full")
    assert entry is not None
    assert entry.timestamp == datetime(2026, 7, 11, 14, 3, 22)
    assert entry.level is LogLevel.ERROR
    assert entry.message == "disk full"


def test_parse_line_keeps_raw_without_newline():
    line = "2026-07-11 14:03:22 INFO started\n"
    entry = parse_line(line)
    assert entry is not None
    assert entry.raw == "2026-07-11 14:03:22 INFO started"


def test_parse_line_level_is_case_insensitive():
    entry = parse_line("2026-07-11 14:03:22 warning low disk")
    assert entry is not None
    assert entry.level is LogLevel.WARNING


def test_parse_line_message_keeps_inner_spacing():
    entry = parse_line("2026-07-11 14:03:22 INFO a  b   c")
    assert entry is not None
    assert entry.message == "a  b   c"


def test_parse_line_rejects_garbage():
    assert parse_line("not a log line") is None
    assert parse_line("") is None


def test_parse_line_rejects_unknown_level():
    assert parse_line("2026-07-11 14:03:22 LOUD something") is None


def test_parse_line_rejects_impossible_date():
    assert parse_line("2026-13-45 14:03:22 INFO x") is None


def test_parse_line_rejects_missing_message():
    assert parse_line("2026-07-11 14:03:22 ERROR") is None


def test_sample_fixture_parses_fully():
    lines = FIXTURE.read_text().splitlines()
    entries = [parse_line(line) for line in lines]
    assert all(entry is not None for entry in entries)
    assert [e.level for e in entries if e][:3] == [
        LogLevel.INFO,
        LogLevel.DEBUG,
        LogLevel.ERROR,
    ]
    assert len(entries) == 7
