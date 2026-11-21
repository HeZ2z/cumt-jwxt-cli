"""Local ddddocr captcha recognition tests."""

import io
import os
import stat
import sys
import types

import pytest

import cumt_jwxt_cli.captcha.ddddocr_ocr as ocr_module
import cumt_jwxt_cli.captcha.manual as manual_module
from cumt_jwxt_cli.errors import CaptchaError


class _Engine:
    def __init__(self, answer: str = "  A1B2  ") -> None:
        self.answer = answer
        self.calls: list[bytes] = []

    def classification(self, image: bytes) -> str:
        self.calls.append(image)
        return self.answer


class _FailedEngine:
    def classification(self, image: bytes) -> str:
        raise RuntimeError("boom")


def test_recognize_captcha_uses_local_engine(monkeypatch) -> None:
    engine = _Engine()
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: engine)

    assert ocr_module.recognize_captcha(b"image") == "A1B2"
    assert engine.calls == [b"image"]


def test_recognize_captcha_rejects_empty_image(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _Engine())

    with pytest.raises(CaptchaError, match="empty"):
        ocr_module.recognize_captcha(b"")


def test_recognize_captcha_rejects_empty_answer(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _Engine("   "))

    with pytest.raises(CaptchaError, match="empty code"):
        ocr_module.recognize_captcha(b"image")


def test_recognize_captcha_wraps_engine_errors(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _FailedEngine())

    with pytest.raises(CaptchaError, match="Captcha recognition failed"):
        ocr_module.recognize_captcha(b"image")


def _capture_created_tempfiles(monkeypatch) -> list[tuple[str, int]]:
    created: list[tuple[str, int]] = []
    real_mkstemp = manual_module.tempfile.mkstemp

    def recording_mkstemp(*, suffix: str) -> tuple[int, str]:
        fd, path = real_mkstemp(suffix=suffix)
        created.append((path, stat.S_IMODE(os.stat(path).st_mode)))
        return fd, path

    monkeypatch.setattr(manual_module.tempfile, "mkstemp", recording_mkstemp)
    return created


def _install_fake_msvcrt(monkeypatch, chars: list[str]) -> None:
    queue = list(chars)
    module = types.ModuleType("msvcrt")
    module.kbhit = lambda: bool(queue)
    module.getwch = lambda: queue.pop(0)
    monkeypatch.setitem(sys.modules, "msvcrt", module)


def test_recognize_captcha_falls_back_to_manual_input(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _FailedEngine())

    stdin = io.StringIO("  ab 12 \n")
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr(stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        manual_module,
        "select",
        lambda readers, writers, errors, timeout: ([stdin], [], []),
    )
    created = _capture_created_tempfiles(monkeypatch)

    assert ocr_module.recognize_captcha(b"image", manual_timeout_seconds=60) == "ab12"
    assert len(created) == 1
    path, mode = created[0]
    assert not os.path.exists(path)
    if os.name != "nt":
        assert mode == 0o600


def test_manual_input_times_out_and_removes_temp_file(monkeypatch) -> None:
    stdin = io.StringIO("")
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr(manual_module, "select", lambda *args: ([], [], []))
    created = _capture_created_tempfiles(monkeypatch)

    with pytest.raises(CaptchaError, match="timed out"):
        manual_module.manual_captcha_input(b"image", 1)

    assert len(created) == 1
    assert not os.path.exists(created[0][0])


def test_manual_input_wraps_stdin_oserror(monkeypatch) -> None:
    stdin = io.StringIO("")
    monkeypatch.setattr("sys.stdin", stdin)

    def failing_select(*args: object) -> tuple[list, list, list]:
        raise OSError("bad file descriptor")

    monkeypatch.setattr(manual_module, "select", failing_select)
    created = _capture_created_tempfiles(monkeypatch)

    with pytest.raises(CaptchaError, match="unavailable"):
        manual_module.manual_captcha_input(b"image", 1)

    assert len(created) == 1
    assert not os.path.exists(created[0][0])


def test_manual_input_wraps_tempfile_write_errors(monkeypatch) -> None:
    def failing_write(fd: int, data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(manual_module.os, "write", failing_write)
    created = _capture_created_tempfiles(monkeypatch)

    with pytest.raises(CaptchaError, match="prepare the captcha image"):
        manual_module.manual_captcha_input(b"image", 1)

    assert len(created) == 1
    assert not os.path.exists(created[0][0])


def test_windows_reader_collects_line(monkeypatch) -> None:
    monkeypatch.setattr(manual_module.os, "name", "nt")
    monkeypatch.setattr(manual_module.time, "monotonic", lambda: 0.0)
    _install_fake_msvcrt(monkeypatch, ["a", "b", "\r"])

    assert manual_module._read_line_with_timeout(5) == "ab"


def test_windows_reader_times_out(monkeypatch) -> None:
    monkeypatch.setattr(manual_module.os, "name", "nt")
    ticks = iter([0.0, 0.0, 100.0])
    monkeypatch.setattr(manual_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(manual_module.time, "sleep", lambda _: None)
    _install_fake_msvcrt(monkeypatch, [])

    with pytest.raises(CaptchaError, match="timed out"):
        manual_module._read_line_with_timeout(1)


def test_recognize_captcha_rejects_manual_fallback_without_tty(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _FailedEngine())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(CaptchaError, match="Captcha recognition failed"):
        ocr_module.recognize_captcha(b"image", manual_timeout_seconds=60)
