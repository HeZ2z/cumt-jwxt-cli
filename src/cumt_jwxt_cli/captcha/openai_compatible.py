"""OpenAI-compatible captcha recognition."""

from __future__ import annotations

import base64
import os
import sys
from collections.abc import Callable
from select import select
from tempfile import NamedTemporaryFile
from typing import Any

from openai import OpenAI

from cumt_jwxt_cli.errors import CaptchaError
from cumt_jwxt_cli.models import OpenAICompatibleConfig


def recognize_captcha(
    image_bytes: bytes,
    config: OpenAICompatibleConfig,
    *,
    client_factory: Callable[..., Any] = OpenAI,
    manual_timeout_seconds: int | None = None,
) -> str:
    """Recognize a captcha image through an OpenAI-compatible chat endpoint."""

    _validate_config(config)
    if not image_bytes:
        raise CaptchaError("Captcha image is empty.")

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    try:
        client = client_factory(api_key=config.api_key, base_url=config.base_url)
        completion = client.chat.completions.create(
            model=config.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Read this captcha. Return only the characters, "
                                "without spaces or explanation."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                }
            ],
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001 - external SDK exceptions vary.
        if manual_timeout_seconds is not None and sys.stdin.isatty():
            return _manual_captcha_input(image_bytes, manual_timeout_seconds)
        raise CaptchaError("Captcha recognition failed.") from exc

    answer = completion.choices[0].message.content
    if not isinstance(answer, str) or not answer.strip():
        raise CaptchaError("Captcha recognition returned an empty code.")
    return "".join(answer.split())


def _manual_captcha_input(image_bytes: bytes, timeout_seconds: int) -> str:
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


def _validate_config(config: OpenAICompatibleConfig) -> None:
    missing = []
    if not config.base_url:
        missing.append("base_url")
    if not config.api_key:
        missing.append("api_key")
    if not config.model:
        missing.append("model")
    if missing:
        raise CaptchaError(
            "Missing OpenAI-compatible captcha configuration: " + ", ".join(missing)
        )
