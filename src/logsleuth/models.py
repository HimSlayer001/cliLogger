"""Data models for logsleuth."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Log severity levels, ordered from least to most severe."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_string(cls, value: str) -> "LogLevel":
        """Parse a level from raw log text, case-insensitively."""
        try:
            return cls(value.upper())
        except ValueError as exc:
            raise ValueError(f"Unknown log level: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single parsed log line."""

    timestamp: datetime
    level: LogLevel
    message: str
    raw: str  # original unparsed line, kept for debugging/grep

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("LogEntry message cannot be empty")

    def is_error(self) -> bool:
        return self.level in (LogLevel.ERROR, LogLevel.CRITICAL)