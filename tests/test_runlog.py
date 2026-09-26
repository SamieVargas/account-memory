"""The start, status and completion lines every entry point prints."""

import io
import sys

import pytest

from core import runlog


def lines(capsys):
    return capsys.readouterr().err.strip().splitlines()


def test_completed_line_with_elapsed(capsys):
    assert runlog.run(lambda: runlog.status("working"), "demo") == 0
    out = lines(capsys)
    assert out[0].startswith("▶ [") and out[0].endswith("demo started")
    assert "· [" in out[1] and out[1].endswith("working")
    assert out[-1].startswith("✓ [") and "demo completed in" in out[-1]


def test_nonzero_interrupt_and_failure(capsys):
    assert runlog.run(lambda: 2, "demo") == 2
    assert "demo stopped with exit code 2" in lines(capsys)[-1]
    assert runlog.run(lambda: 130, "demo") == 130
    assert "interrupted" in lines(capsys)[-1]

    def boom():
        raise ValueError("bad input")
    with pytest.raises(ValueError):
        runlog.run(boom, "demo")
    last = lines(capsys)[-1]
    assert last.startswith("✗ [") and "demo failed after" in last and "ValueError: bad input" in last

    def ctrl_c():
        raise KeyboardInterrupt
    assert runlog.run(ctrl_c, "demo") == runlog.INTERRUPTED


def test_progress_every_n_and_last(capsys):
    for i in range(1, 26):
        runlog.progress(i, 25, "items", every=10)
    out = lines(capsys)
    assert [l.split("] ")[1].split(" ")[0] for l in out] == ["10/25", "20/25", "25/25"]


def test_ascii_fallback(monkeypatch):
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stderr", stream)
    runlog.run(lambda: 0, "demo")
    stream.flush()
    text = buf.getvalue().decode("cp1252")
    assert text.startswith("> [") and "OK [" in text


def test_elapsed_format():
    assert runlog.elapsed(3.24) == "3.2s" and runlog.elapsed(125) == "2m 05s" and runlog.elapsed(3725) == "1h 02m 05s"


def test_broken_pipe_is_a_normal_finish(capsys, monkeypatch):
    def piped():
        raise BrokenPipeError
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    assert runlog.run(piped, "demo") == 0
    assert "output closed early" in lines(capsys)[-1]
