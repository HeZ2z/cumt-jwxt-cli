"""Local ddddocr captcha recognition tests."""

import io

import pytest

import cumt_jwxt_cli.captcha.ddddocr_ocr as ocr_module
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


def test_recognize_captcha_falls_back_to_manual_input(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _FailedEngine())

    def fake_named_tempfile(*, suffix: str, delete: bool):
        class TempFile:
            name = str(tmp_path / f"captcha{suffix}")

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def write(self, data: bytes) -> int:
                return len(data)

        return TempFile()

    stdin = io.StringIO("  ab 12 \n")
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr(stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        "cumt_jwxt_cli.captcha.openai_compatible.select",
        lambda readers, writers, errors, timeout: ([stdin], [], []),
    )
    monkeypatch.setattr(
        "cumt_jwxt_cli.captcha.openai_compatible.NamedTemporaryFile",
        fake_named_tempfile,
    )

    assert ocr_module.recognize_captcha(b"image", manual_timeout_seconds=60) == "ab12"


def test_recognize_captcha_rejects_manual_fallback_without_tty(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: _FailedEngine())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(CaptchaError, match="Captcha recognition failed"):
        ocr_module.recognize_captcha(b"image", manual_timeout_seconds=60)
