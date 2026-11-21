"""Manual captcha input fallback."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from select import select

from cumt_jwxt_cli.errors import CaptchaError

_POLL_INTERVAL_SECONDS = 0.05


def manual_captcha_input(image_bytes: bytes, timeout_seconds: int) -> str:
    timeout_seconds = max(1, timeout_seconds)
    captcha_path = _write_temp_captcha(image_bytes)
    try:
        print(
            "Captcha recognition failed. Open this temporary image and enter "
            f"the code within {timeout_seconds} seconds: {captcha_path}",
            file=sys.stderr,
        )
        answer = _read_line_with_timeout(timeout_seconds).strip()
        if not answer:
            raise CaptchaError("Manual captcha input returned an empty code.")
        return "".join(answer.split())
    finally:
        try:
            os.unlink(captcha_path)
        except OSError:
            pass


def _write_temp_captcha(image_bytes: bytes) -> str:
    try:
        fd, path = tempfile.mkstemp(suffix=".jpg")
    except OSError as exc:
        raise CaptchaError(
            "Unable to prepare the captcha image for manual input."
        ) from exc
    try:
        os.write(fd, image_bytes)
    except OSError as exc:
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise CaptchaError(
            "Unable to prepare the captcha image for manual input."
        ) from exc
    os.close(fd)
    return path


def _read_line_with_timeout(timeout_seconds: int) -> str:
    if os.name == "nt":
        return _read_line_windows(timeout_seconds)
    return _read_line_posix(timeout_seconds)


def _read_line_posix(timeout_seconds: int) -> str:
    try:
        ready, _, _ = select([sys.stdin], [], [], timeout_seconds)
    except (OSError, ValueError) as exc:
        raise CaptchaError("Manual captcha input is unavailable.") from exc
    if not ready:
        raise CaptchaError("Manual captcha input timed out.")
    try:
        return sys.stdin.readline()
    except OSError as exc:
        raise CaptchaError("Manual captcha input is unavailable.") from exc


def _read_line_windows(timeout_seconds: int) -> str:
    import msvcrt

    deadline = time.monotonic() + timeout_seconds
    chars: list[str] = []
    while time.monotonic() < deadline:
        try:
            if not msvcrt.kbhit():
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            char = msvcrt.getwch()
        except OSError as exc:
            raise CaptchaError("Manual captcha input is unavailable.") from exc
        if char in ("\r", "\n"):
            sys.stderr.write("\n")
            sys.stderr.flush()
            return "".join(chars)
        if char == "\x03":
            raise CaptchaError("Manual captcha input was cancelled.")
        if char == "\x1a":
            return "".join(chars)
        if char == "\x08":
            if chars:
                chars.pop()
                sys.stderr.write("\b \b")
                sys.stderr.flush()
            continue
        chars.append(char)
        sys.stderr.write(char)
        sys.stderr.flush()
    raise CaptchaError("Manual captcha input timed out.")
