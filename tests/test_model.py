from datetime import datetime

import pytest

from logsleuth.models import LogEntry, LogLevel


def test_log_level_from_string_case_insensitive():
    assert LogLevel.from_string("error") == LogLevel.ERROR
    assert LogLevel.from_string("INFO") == LogLevel.INFO


def test_log_level_from_string_invalid():
    with pytest.raises(ValueError):
        LogLevel.from_string("NOT_A_LEVEL")


def test_log_entry_is_error():
    entry = LogEntry(
        timestamp=datetime.now(),
        level=LogLevel.ERROR,
        message="disk full",
        raw="2026-07-11 ERROR disk full",
    )
    assert entry.is_error()


def test_log_entry_rejects_empty_message():
    with pytest.raises(ValueError):
        LogEntry(timestamp=datetime.now(), level=LogLevel.INFO, message="   ", raw="")