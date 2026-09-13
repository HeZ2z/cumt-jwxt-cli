"""Manual captcha input fallback."""

from __future__ import annotations

import os
import sys
from select import select
from tempfile import NamedTemporaryFile

from cumt_jwxt_cli.errors import CaptchaError


def manual_captcha_input(image_bytes: bytes, timeout_seconds: int) -> str:
    timeout_seconds = max(1, timeout_seconds)
    captcha_path = _write_temp_captcha(image_bytes)
    try:
        print(
            "Captcha recognition failed. Open this temporary image and enter "
            f"the code within {timeout_seconds} seconds: {captcha_path}",
            file=sys.stderr,
        )
        ready, _, _ = select([sys.stdin], [], [], timeout_seconds)
        if not ready:
            raise CaptchaError("Manual captcha input timed out.")
        answer = sys.stdin.readline().strip()
        if not answer:
            raise CaptchaError("Manual captcha input returned an empty code.")
        return "".join(answer.split())
    finally:
        try:
            os.unlink(captcha_path)
        except OSError:
            pass


def _write_temp_captcha(image_bytes: bytes) -> str:
    with NamedTemporaryFile(suffix=".jpg", delete=False) as file:
        file.write(image_bytes)
        return file.name
