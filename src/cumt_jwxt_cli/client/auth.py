"""JWXT authentication flow."""

from __future__ import annotations

import time
from collections.abc import Callable

from bs4 import BeautifulSoup

from cumt_jwxt_cli.errors import AuthError, CaptchaError
from cumt_jwxt_cli.models import AppConfig

LOGIN_PATH = "/xtgl/login_slogin.html"


def extract_csrf_token(login_html: str) -> str:
    """Extract the login CSRF token from a JWXT login page."""

    soup = BeautifulSoup(login_html, "html.parser")
    token_input = soup.find("input", attrs={"name": "csrftoken"})
    token = token_input.get("value") if token_input is not None else None
    if not isinstance(token, str) or not token.strip():
        raise AuthError("JWXT login page did not contain a CSRF token.")
    return token.strip()


def login(
    config: AppConfig,
    client: object,
    *,
    recognize_captcha: Callable[[bytes, AppConfig], str],
    max_captcha_attempts: int = 3,
) -> dict[str, str]:
    """Log in to JWXT and return a serializable cookie snapshot when available.

    Retries up to *max_captcha_attempts* times on captcha recognition or
    login-submission failure, fetching a fresh captcha image each attempt.
    """

    clear_cookies = getattr(client, "clear_cookies", None)
    last_error: Exception | None = None

    for _ in range(max_captcha_attempts):
        if callable(clear_cookies):
            clear_cookies()

        try:
            timestamp_ms = int(time.time() * 1000)
            login_response = client.get(LOGIN_PATH)
            csrf_token = extract_csrf_token(login_response.text)

            captcha_response = client.get(f"/kaptcha?time={timestamp_ms}")
            captcha_code = recognize_captcha(captcha_response.content, config).strip()
            if not captcha_code:
                raise CaptchaError("Captcha recognition returned an empty code.")

            response = client.post(
                LOGIN_PATH,
                data={
                    "csrftoken": csrf_token,
                    "language": "zh_CN",
                    "ydType": "",
                    "yhm": config.cumt.username,
                    "mm": config.cumt.password,
                    "yzm": captcha_code,
                },
            )
            if _looks_logged_in(response):
                cookies = getattr(client, "cookies", None)
                if callable(cookies):
                    return cookies()
                return {}

            last_error = AuthError(
                "JWXT login failed; credentials or captcha may be invalid."
            )
        except AuthError:
            raise
        except CaptchaError as exc:
            last_error = exc

    raise AuthError(
        "JWXT login failed after multiple attempts; "
        "credentials or captcha may be invalid."
    ) from last_error


def _looks_logged_in(response: object) -> bool:
    status_code = getattr(response, "status_code", None)
    if status_code in {301, 302, 303, 307, 308}:
        return True

    html = getattr(response, "text", "")
    if not isinstance(html, str):
        return False
    failure_markers = ("验证码", "用户名", "密码", "错误", "失败")
    if any(marker in html for marker in failure_markers):
        return False
    return bool(html.strip())
