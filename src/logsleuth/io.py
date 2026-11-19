"""Read log files lazily and collect the lines that could not be parsed."""

import gzip
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from logsleuth.models import LogEntry
from logsleuth.parser import ParseError, parse_line

STDIN = "-"


@dataclass(frozen=True, slots=True)
class SkippedLine:
    """A non-blank line that no log format could parse."""

    line_number: int  # 1-based, as in an editor
    line: str
    reason: str


@contextmanager
def _open_text(source: str | Path, encoding: str) -> Iterator[TextIO]:
    """Open a path (plain or .gz) or stdin ("-") as text.

    Undecodable bytes are replaced rather than aborting the whole read.
    """
    if str(source) == STDIN:
        yield sys.stdin
        return

    path = Path(source)
    if path.suffix == ".gz":
        handle: TextIO = gzip.open(path, "rt", encoding=encoding, errors="replace")
    else:
        handle = path.open("r", encoding=encoding, errors="replace")
    with handle:
        yield handle


class LogReader:
    """Stream LogEntry objects from a log source.

    Nothing is opened until the reader is iterated, and lines are parsed one
    at a time, so large files are never held in memory. Blank lines are
    ignored; any other line that fails to parse is recorded in ``skipped``
    (reset at the start of each iteration) instead of stopping the read.
    """

    def __init__(self, source: str | Path, *, encoding: str = "utf-8") -> None:
        self.source = source
        self.encoding = encoding
        self.skipped: list[SkippedLine] = []

    def __iter__(self) -> Iterator[LogEntry]:
        self.skipped = []
        with _open_text(self.source, self.encoding) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield parse_line(line)
                except ParseError as exc:
                    self.skipped.append(
                        SkippedLine(line_number, exc.line, exc.reason)
                    )
