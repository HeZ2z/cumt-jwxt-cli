"""Authentication boundary tests."""

import json

import pytest

from cumt_jwxt_cli.client.auth import (
    extract_csrf_token,
    login,
    should_encrypt_password,
)
from cumt_jwxt_cli.errors import AuthError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
)


class _Response:
    def __init__(self, *, text: str = "", content: bytes = b"", status_code: int = 200):
        self.text = text
        self.content = content
        self.status_code = status_code

    def json(self) -> object:
        return json.loads(self.text)


class _Client:
    def __init__(self, *, login_html: str | None = None) -> None:
        self.login_html = login_html or '<input name="csrftoken" value="TOKEN">'
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.clear_cookie_calls = 0
        self.public_key_fetches = 0

    def get(self, path: str) -> _Response:
        if path.startswith("/xtgl/login_slogin.html"):
            return _Response(text=self.login_html)
        if path.startswith("/kaptcha"):
            return _Response(content=b"captcha-bytes")
        if path.startswith("/xtgl/login_getPublicKey.html"):
            self.public_key_fetches += 1
            return _Response(text='{"modulus": "AQ==", "exponent": "AQ=="}')
        raise AssertionError(path)

    def post(self, path: str, *, data: dict[str, str]) -> _Response:
        self.posts.append((path, data))
        return _Response(text="首页")

    def clear_cookies(self) -> None:
        self.clear_cookie_calls += 1


@pytest.fixture(autouse=True)
def _fake_password_encryption(monkeypatch) -> None:
    monkeypatch.setattr(
        "cumt_jwxt_cli.client.auth.encrypt_password",
        lambda password, modulus, exponent: "ENCRYPTED",
    )


def _config() -> AppConfig:
    return AppConfig(
        config_path=__file__,  # type: ignore[arg-type]
        cumt=CUMTConfig(username="student", password="secret"),
        query=QueryConfig(year="2024", semester="12"),
        http=HTTPConfig(30, 2, 1.5),
        grades=GradesConfig(True, 3),
        captcha=CaptchaConfig(
            "openai_compatible",
            60,
            OpenAICompatibleConfig("", "", ""),
        ),
        notify=NotifyConfig(False, "", 465, "", "", "", ()),
        logging=LoggingConfig(14),
        output=OutputConfig(
            save_json=False, save_report=False, save_ics=False, output_dir=""
        ),
    )


def test_extract_csrf_token_reads_login_form_token() -> None:
    assert extract_csrf_token('<input name="csrftoken" value=" abc ">') == "abc"


def test_extract_csrf_token_rejects_missing_token() -> None:
    with pytest.raises(AuthError, match="CSRF token"):
        extract_csrf_token("<html></html>")


def test_login_submits_captcha_and_credentials() -> None:
    client = _Client()

    login(
        _config(),
        client,
        recognize_captcha=lambda image, config: "1234",
    )

    assert client.posts == [
        (
            "/xtgl/login_slogin.html",
            {
                "csrftoken": "TOKEN",
                "language": "zh_CN",
                "ydType": "",
                "yhm": "student",
                "mm": "ENCRYPTED",
                "yzm": "1234",
            },
        )
    ]
    assert client.clear_cookie_calls == 1
    assert client.public_key_fetches == 1


def test_should_encrypt_password_defaults_to_true_without_flag() -> None:
    assert should_encrypt_password('<input name="csrftoken" value="T">') is True


def test_should_encrypt_password_is_false_only_for_zero() -> None:
    assert should_encrypt_password('<input name="mmsfjm" value="0">') is False
    assert should_encrypt_password('<input name="mmsfjm" value="1">') is True


def test_login_skips_password_encryption_when_disabled() -> None:
    client = _Client(
        login_html=(
            '<input name="csrftoken" value="TOKEN"><input name="mmsfjm" value="0">'
        )
    )

    login(_config(), client, recognize_captcha=lambda image, config: "1234")

    assert client.posts[0][1]["mm"] == "secret"
    assert client.public_key_fetches == 0


def test_login_rejects_failed_status() -> None:
    class FailedClient(_Client):
        def post(self, path: str, *, data: dict[str, str]) -> _Response:
            return _Response(text="验证码错误")

    with pytest.raises(AuthError, match="after multiple attempts"):
        login(_config(), FailedClient(), recognize_captcha=lambda image, config: "1234")


def test_login_accepts_redirect_after_successful_post() -> None:
    class RedirectClient(_Client):
        def post(self, path: str, *, data: dict[str, str]) -> _Response:
            self.posts.append((path, data))
            return _Response(status_code=302)

    login(
        _config(),
        RedirectClient(),
        recognize_captcha=lambda image, config: "1234",
    )


def test_login_retries_on_failed_captcha_then_succeeds() -> None:
    class RetryThenSucceedClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.post_count = 0

        def post(self, path: str, *, data: dict[str, str]) -> _Response:
            self.posts.append((path, data))
            self.post_count += 1
            if self.post_count == 1:
                return _Response(text="验证码错误")
            return _Response(status_code=302)

    client = RetryThenSucceedClient()

    login(
        _config(),
        client,
        recognize_captcha=lambda image, config: "1234",
    )

    assert len(client.posts) == 2
    assert client.clear_cookie_calls == 2
