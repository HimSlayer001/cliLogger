import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from logsleuth.cli import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, EXIT_USAGE, main

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample.log")


def test_summary_prints_totals_levels_and_range(capsys: pytest.CaptureFixture[str]):
    assert main(["summary", FIXTURE]) == 0
    out = capsys.readouterr().out
    assert "Entries: 7" in out
    assert "Time range: 2026-07-11 14:03:20 to 2026-07-11 14:04:40" in out
    assert "ERROR    2" in out
    assert "CRITICAL 1" in out


def test_summary_lists_top_messages(capsys: pytest.CaptureFixture[str]):
    main(["summary", FIXTURE, "--top", "2"])
    out = capsys.readouterr().out
    assert out.count("\n  ") >= 2
    assert "Top messages:" in out


def test_summary_top_zero_hides_messages(capsys: pytest.CaptureFixture[str]):
    main(["summary", FIXTURE, "--top", "0"])
    assert "Top messages:" not in capsys.readouterr().out


def test_summary_reports_bursts(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # One error a minute as a baseline, then ten in a single minute.
    lines = [f"2026-07-11 10:0{m}:00 ERROR baseline" for m in range(1, 8)]
    lines += [f"2026-07-11 10:08:{s:02d} ERROR boom {s}" for s in range(10)]
    path = tmp_path / "burst.log"
    path.write_text("\n".join(lines) + "\n")
    main(["summary", str(path)])
    out = capsys.readouterr().out
    assert "Error bursts:" in out
    assert "2026-07-11 10:08:00 to 2026-07-11 10:09:00: 10 errors" in out


def test_summary_without_bursts_omits_section(capsys: pytest.CaptureFixture[str]):
    main(["summary", FIXTURE])
    assert "Error bursts:" not in capsys.readouterr().out


def test_summary_rejects_bad_numbers(capsys: pytest.CaptureFixture[str]):
    assert main(["summary", FIXTURE, "--top", "-1"]) == 2
    assert main(["summary", FIXTURE, "--bucket", "0"]) == 2
    assert "must be" in capsys.readouterr().err


def test_filter_by_level(capsys: pytest.CaptureFixture[str]):
    assert main(["filter", FIXTURE, "--level", "error"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert lines[0].endswith("ERROR disk full on /dev/sda1")


def test_filter_level_is_case_insensitive(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--level", "CRITICAL"])
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_filter_contains_is_repeatable_and_anded(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--contains", "db-1", "--contains", "refused"])
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["2026-07-11 14:03:31 ERROR connection to db-1 refused"]


def test_filter_regex(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--regex", r"\d+ms$"])
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_filter_since_and_until(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--since", "2026-07-11T14:03:25", "--until", "2026-07-11 14:04:02"])
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_filter_rejects_bad_arguments():
    for bad in (
        ["filter", FIXTURE, "--level", "loud"],
        ["filter", FIXTURE, "--since", "yesterday"],
        ["filter", FIXTURE, "--regex", "(unclosed"],
    ):
        with pytest.raises(SystemExit) as info:
            main(bad)
        assert info.value.code == 2


def test_filter_reads_stdin_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "stdin", io.StringIO("2026-07-11 14:03:22 ERROR x\n"))
    assert main(["filter", "--level", "error"]) == 0
    assert capsys.readouterr().out == "2026-07-11 14:03:22 ERROR x\n"


def test_skipped_lines_are_reported_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "mixed.log"
    path.write_text("junk\n2026-07-11 14:03:22 INFO ok\n")
    main(["filter", str(path)])
    captured = capsys.readouterr()
    assert captured.out == "2026-07-11 14:03:22 INFO ok\n"
    assert "skipped 1 unparseable line(s)" in captured.err


def test_missing_file_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert main(["summary", str(tmp_path / "nope.log")]) == 1
    assert "no such file" in capsys.readouterr().err


def test_command_is_required():
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2


def test_python_dash_m_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "logsleuth", "filter", FIXTURE, "--level", "critical"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "out of memory" in result.stdout


# --- JSON output ---


def test_summary_json(capsys: pytest.CaptureFixture[str]):
    assert main(["summary", FIXTURE, "--format", "json", "--top", "1"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total"] == 7
    assert data["first_timestamp"] == "2026-07-11T14:03:20"
    assert data["levels"]["ERROR"] == 2
    assert list(data["levels"]) == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    assert len(data["top_messages"]) == 1
    assert data["bursts"] == []
    assert data["skipped"] == 0


def test_summary_json_empty_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    main(["summary", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["total"] == 0
    assert data["first_timestamp"] is None


def test_filter_json_is_one_object_per_line(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--level", "critical", "--format", "json"])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "timestamp": "2026-07-11T14:04:40",
        "level": "CRITICAL",
        "message": "out of memory, shutting down",
        "raw": "2026-07-11 14:04:40 CRITICAL out of memory, shutting down",
    }


def test_json_keeps_non_ascii_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "u.log"
    path.write_text("2026-07-11 14:03:22 INFO café ready\n", encoding="utf-8")
    main(["filter", str(path), "--format", "json"])
    assert "café" in capsys.readouterr().out


# --- colour ---


def test_color_always_paints_filter_lines(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--level", "critical", "--color", "always"])
    out = capsys.readouterr().out
    assert out.startswith("\033[1;31m2026-07-11 14:04:40 CRITICAL")
    assert out.rstrip().endswith("\033[0m")


def test_color_never_and_pipes_are_plain(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--level", "critical", "--color", "never"])
    assert "\033" not in capsys.readouterr().out
    main(["filter", FIXTURE, "--level", "critical"])  # auto, stdout is a pipe
    assert "\033" not in capsys.readouterr().out


def test_no_color_env_beats_auto(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    main(["filter", FIXTURE, "--level", "critical"])
    assert "\033" not in capsys.readouterr().out


def test_json_is_never_coloured(capsys: pytest.CaptureFixture[str]):
    main(["filter", FIXTURE, "--format", "json", "--color", "always"])
    assert "\033" not in capsys.readouterr().out


def test_summary_colours_headings_when_asked(capsys: pytest.CaptureFixture[str]):
    main(["summary", FIXTURE, "--color", "always"])
    assert "\033[1mEntries:\033[0m 7" in capsys.readouterr().out


# --- top ---


def test_top_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = tmp_path / "t.log"
    path.write_text(
        "2026-07-11 14:03:22 ERROR retry 1\n"
        "2026-07-11 14:03:23 ERROR retry 2\n"
        "2026-07-11 14:03:24 INFO started\n"
    )
    assert main(["top", str(path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "    2  retry <N>"
    assert lines[1] == "    1  started"


def test_top_number_and_level(capsys: pytest.CaptureFixture[str]):
    main(["top", FIXTURE, "-n", "1", "--level", "error"])
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_top_json(capsys: pytest.CaptureFixture[str]):
    main(["top", FIXTURE, "--format", "json", "-n", "2"])
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2
    assert set(data[0]) == {"message", "count"}


def test_top_rejects_negative_number(capsys: pytest.CaptureFixture[str]):
    assert main(["top", FIXTURE, "-n", "-1"]) == EXIT_USAGE
    assert "--number must be" in capsys.readouterr().err


# --- exit codes and errors ---


def test_exit_code_constants():
    assert (EXIT_OK, EXIT_ERROR, EXIT_USAGE) == (0, 1, 2)


def test_directory_as_input_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert main(["summary", str(tmp_path)]) == EXIT_ERROR
    assert "cannot read" in capsys.readouterr().err


def test_corrupt_gzip_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = tmp_path / "bad.log.gz"
    path.write_bytes(b"this is not gzip data")
    assert main(["summary", str(path)]) == EXIT_ERROR
    assert "corrupt gzip" in capsys.readouterr().err


def test_broken_pipe_is_quiet(monkeypatch: pytest.MonkeyPatch):
    def boom(*args: object, **kwargs: object) -> None:
        raise BrokenPipeError

    monkeypatch.setattr("builtins.print", boom)
    assert main(["filter", FIXTURE]) == EXIT_OK


def test_keyboard_interrupt_exits_130(monkeypatch: pytest.MonkeyPatch):
    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.print", interrupt)
    assert main(["filter", FIXTURE]) == EXIT_INTERRUPTED


def test_summary_text_on_empty_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main(["summary"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Entries: 0" in out
    assert "Time range" not in out
    assert "Top messages" not in out
