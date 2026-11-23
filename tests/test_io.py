import gzip
import io
import sys
from pathlib import Path

import pytest

from logsleuth.io import LogReader, SkippedLine
from logsleuth.models import LogLevel

FIXTURE = Path(__file__).parent / "fixtures" / "sample.log"


def test_reads_plain_file():
    entries = list(LogReader(FIXTURE))
    assert len(entries) == 7
    assert entries[2].level is LogLevel.ERROR
    assert entries[2].message == "disk full on /dev/sda1"


def test_accepts_str_path():
    assert len(list(LogReader(str(FIXTURE)))) == 7


def test_reads_gzip_file(tmp_path: Path):
    path = tmp_path / "app.log.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("2026-07-11 14:03:22 ERROR disk full\n")
        handle.write("2026-07-11 14:03:23 INFO recovered\n")
    entries = list(LogReader(path))
    assert [e.message for e in entries] == ["disk full", "recovered"]


def test_reads_stdin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("2026-07-11 14:03:22 WARNING low disk\n")
    )
    entries = list(LogReader("-"))
    assert len(entries) == 1
    assert entries[0].level is LogLevel.WARNING


def test_stdin_is_left_open(monkeypatch: pytest.MonkeyPatch):
    stream = io.StringIO("2026-07-11 14:03:22 INFO a\n")
    monkeypatch.setattr(sys, "stdin", stream)
    list(LogReader("-"))
    assert not stream.closed


def test_is_lazy_until_iterated(tmp_path: Path):
    reader = LogReader(tmp_path / "missing.log")  # constructing must not open
    with pytest.raises(FileNotFoundError):
        next(iter(reader))


def test_streams_one_entry_at_a_time(tmp_path: Path):
    path = tmp_path / "big.log"
    path.write_text("".join(f"2026-07-11 14:03:22 INFO line {i}\n" for i in range(1000)))
    iterator = iter(LogReader(path))
    assert next(iterator).message == "line 0"
    assert next(iterator).message == "line 1"


def test_collects_skipped_lines_with_numbers(tmp_path: Path):
    path = tmp_path / "mixed.log"
    path.write_text(
        "2026-07-11 14:03:22 INFO ok\n"
        "garbage here\n"
        "2026-07-11 14:03:23 LOUD nope\n"
        "2026-07-11 14:03:24 ERROR bad\n"
    )
    reader = LogReader(path)
    entries = list(reader)
    assert [e.message for e in entries] == ["ok", "bad"]
    assert reader.skipped == [
        SkippedLine(2, "garbage here", "unrecognised line format"),
        SkippedLine(3, "2026-07-11 14:03:23 LOUD nope", "unknown log level"),
    ]


def test_blank_lines_are_ignored_not_reported(tmp_path: Path):
    path = tmp_path / "blank.log"
    path.write_text("\n2026-07-11 14:03:22 INFO ok\n   \n\n")
    reader = LogReader(path)
    assert len(list(reader)) == 1
    assert reader.skipped == []


def test_skipped_resets_on_each_iteration(tmp_path: Path):
    path = tmp_path / "again.log"
    path.write_text("junk\n2026-07-11 14:03:22 INFO ok\n")
    reader = LogReader(path)
    list(reader)
    list(reader)
    assert len(reader.skipped) == 1


def test_undecodable_bytes_do_not_abort(tmp_path: Path):
    path = tmp_path / "bin.log"
    path.write_bytes(b"2026-07-11 14:03:22 INFO caf\xe9 ok\n")
    entries = list(LogReader(path))
    assert len(entries) == 1
    assert entries[0].message.startswith("caf")
