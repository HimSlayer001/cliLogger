"""Terminal colour helpers."""

from collections.abc import Mapping
from typing import TextIO

from logsleuth.models import LogLevel

RESET = "\033[0m"
BOLD = "1"

# SGR codes per level; INFO stays uncoloured so ordinary lines read as plain text.
LEVEL_CODES: dict[LogLevel, str | None] = {
    LogLevel.DEBUG: "2",  # dim
    LogLevel.INFO: None,
    LogLevel.WARNING: "33",  # yellow
    LogLevel.ERROR: "31",  # red
    LogLevel.CRITICAL: "1;31",  # bold red
}


def use_color(mode: str, stream: TextIO, env: Mapping[str, str]) -> bool:
    """Decide whether to emit colour.

    ``always`` and ``never`` are absolute. ``auto`` colours only a terminal,
    and honours NO_COLOR (https://no-color.org) and TERM=dumb.
    """
    if mode == "always":
        return True
    if mode == "never":
        return False
    if env.get("NO_COLOR"):
        return False
    if env.get("TERM") == "dumb":
        return False
    return stream.isatty()


def paint(text: str, code: str | None, enabled: bool) -> str:
    """Wrap text in an SGR code when colour is enabled and a code is given."""
    if not enabled or not code:
        return text
    return f"\033[{code}m{text}{RESET}"
