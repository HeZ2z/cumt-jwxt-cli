"""OpenAI-compatible captcha recognition tests."""

import io

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


def test_recognize_captcha_falls_back_to_manual_input(
    tmp_path,
    monkeypatch,
) -> None:
    class FailedClient(_Client):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("boom")

    created_paths: list[object] = []

    def fake_named_tempfile(*, suffix: str, delete: bool):
        class TempFile:
            name = str(tmp_path / f"captcha{suffix}")

            def __enter__(self):
                created_paths.append(self.name)
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

    answer = recognize_captcha(
        b"image",
        _config(),
        client_factory=FailedClient,
        manual_timeout_seconds=60,
    )

    assert answer == "ab12"
    assert created_paths == [str(tmp_path / "captcha.jpg")]


def test_recognize_captcha_rejects_manual_fallback_without_tty(monkeypatch) -> None:
    class FailedClient(_Client):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(CaptchaError, match="Captcha recognition failed"):
        recognize_captcha(
            b"image",
            _config(),
            client_factory=FailedClient,
        )


def test_recognize_captcha_times_out_manual_input(monkeypatch) -> None:
    class FailedClient(_Client):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(
        "cumt_jwxt_cli.captcha.openai_compatible.select",
        lambda readers, writers, errors, timeout: ([], [], []),
    )

    with pytest.raises(CaptchaError, match="Manual captcha input timed out"):
        recognize_captcha(
            b"image",
            _config(),
            client_factory=FailedClient,
            manual_timeout_seconds=1,
        )


def test_recognize_captcha_reads_manual_input_with_select(monkeypatch) -> None:
    class FailedClient(_Client):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("boom")

    stdin = io.StringIO("xy 99\n")
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr(stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        "cumt_jwxt_cli.captcha.openai_compatible.select",
        lambda readers, writers, errors, timeout: ([stdin], [], []),
    )

    assert (
        recognize_captcha(
            b"image",
            _config(),
            client_factory=FailedClient,
            manual_timeout_seconds=1,
        )
        == "xy99"
    )
