"""Authentication boundary tests."""

import pytest

from cumt_jwxt_cli.client.auth import extract_csrf_token, login
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


class _Client:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.clear_cookie_calls = 0

    def get(self, path: str) -> _Response:
        if path.startswith("/xtgl/login_slogin.html"):
            return _Response(text='<input name="csrftoken" value="TOKEN">')
        if path.startswith("/kaptcha"):
            return _Response(content=b"captcha-bytes")
        raise AssertionError(path)

    def post(self, path: str, *, data: dict[str, str]) -> _Response:
        self.posts.append((path, data))
        return _Response(text="首页")

    def clear_cookies(self) -> None:
        self.clear_cookie_calls += 1


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
        output=OutputConfig(False, False, ""),
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
                "mm": "secret",
                "yzm": "1234",
            },
        )
    ]
    assert client.clear_cookie_calls == 1


def test_login_rejects_failed_status() -> None:
    class FailedClient(_Client):
        def post(self, path: str, *, data: dict[str, str]) -> _Response:
            return _Response(text="验证码错误")

    with pytest.raises(AuthError, match="JWXT login failed"):
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
