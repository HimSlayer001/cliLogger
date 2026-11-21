import io

from logsleuth.render import paint, use_color


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_auto_colours_a_terminal():
    assert use_color("auto", FakeTTY(), {})


def test_auto_does_not_colour_a_pipe():
    assert not use_color("auto", io.StringIO(), {})


def test_auto_respects_no_color():
    assert not use_color("auto", FakeTTY(), {"NO_COLOR": "1"})


def test_empty_no_color_is_ignored():
    assert use_color("auto", FakeTTY(), {"NO_COLOR": ""})


def test_auto_respects_dumb_terminal():
    assert not use_color("auto", FakeTTY(), {"TERM": "dumb"})


def test_always_and_never_are_absolute():
    assert use_color("always", io.StringIO(), {"NO_COLOR": "1"})
    assert not use_color("never", FakeTTY(), {})


def test_paint_wraps_when_enabled():
    assert paint("x", "31", True) == "\033[31mx\033[0m"


def test_paint_is_plain_when_disabled_or_codeless():
    assert paint("x", "31", False) == "x"
    assert paint("x", None, True) == "x"
