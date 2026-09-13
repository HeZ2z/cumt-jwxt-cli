"""Local captcha recognition using ddddocr.

The captcha image is processed entirely in memory on this machine, so no
captcha content is sent to an external service.
"""

from __future__ import annotations

import sys
from typing import Any

from cumt_jwxt_cli.captcha.manual import manual_captcha_input
from cumt_jwxt_cli.errors import CaptchaError

_ocr_engine: Any | None = None


def _get_ocr_engine() -> Any:
    """Return the cached ddddocr engine, creating it on first use.

    ddddocr loads bundled ONNX models and is slow to import, so it is created
    lazily instead of at module import time.
    """

    global _ocr_engine
    if _ocr_engine is None:
        import ddddocr

        _ocr_engine = ddddocr.DdddOcr(show_ad=False)
    return _ocr_engine


def recognize_captcha(
    image_bytes: bytes,
    *,
    manual_timeout_seconds: int | None = None,
) -> str:
    """Recognize a captcha locally with ddddocr."""

    if not image_bytes:
        raise CaptchaError("Captcha image is empty.")

    try:
        answer = _get_ocr_engine().classification(image_bytes)
    except Exception as exc:  # noqa: BLE001 - ddddocr raises varied exceptions.
        if manual_timeout_seconds is not None and sys.stdin.isatty():
            return manual_captcha_input(image_bytes, manual_timeout_seconds)
        raise CaptchaError("Captcha recognition failed.") from exc

    if not isinstance(answer, str) or not answer.strip():
        raise CaptchaError("Captcha recognition returned an empty code.")
    return "".join(answer.split())
