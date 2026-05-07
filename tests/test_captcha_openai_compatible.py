"""OpenAI-compatible captcha recognition tests."""

import pytest

from cumt_jwxt_cli.captcha.openai_compatible import recognize_captcha
from cumt_jwxt_cli.errors import CaptchaError
from cumt_jwxt_cli.models import OpenAICompatibleConfig


class _Message:
    content = "  A1B2  "


class _Choice:
    message = _Message()


class _Completion:
    choices = [_Choice()]


class _Completions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _Completion:
        self.calls.append(kwargs)
        return _Completion()


class _Chat:
    def __init__(self) -> None:
        self.completions = _Completions()


class _Client:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.chat = _Chat()


def _config() -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="vision-model",
    )


def test_recognize_captcha_calls_openai_compatible_client() -> None:
    answer = recognize_captcha(b"image", _config(), client_factory=_Client)

    assert answer == "A1B2"


def test_recognize_captcha_requires_provider_config() -> None:
    with pytest.raises(CaptchaError, match="base_url"):
        recognize_captcha(
            b"image",
            OpenAICompatibleConfig(base_url="", api_key="test-key", model="model"),
            client_factory=_Client,
        )


def test_recognize_captcha_wraps_client_errors() -> None:
    class FailedClient(_Client):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("boom")

    with pytest.raises(CaptchaError, match="Captcha recognition failed"):
        recognize_captcha(b"image", _config(), client_factory=FailedClient)
