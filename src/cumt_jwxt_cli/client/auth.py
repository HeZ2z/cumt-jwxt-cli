"""JWXT authentication flow."""

from __future__ import annotations

import time
from collections.abc import Callable

from bs4 import BeautifulSoup

from cumt_jwxt_cli.client.password_crypto import encrypt_password
from cumt_jwxt_cli.errors import AuthError, CaptchaError
from cumt_jwxt_cli.models import AppConfig

LOGIN_PATH = "/xtgl/login_slogin.html"
PUBLIC_KEY_PATH = "/xtgl/login_getPublicKey.html"


def extract_csrf_token(login_html: str) -> str:
    """Extract the login CSRF token from a JWXT login page."""

    soup = BeautifulSoup(login_html, "html.parser")
    token_input = soup.find("input", attrs={"name": "csrftoken"})
    token = token_input.get("value") if token_input is not None else None
    if not isinstance(token, str) or not token.strip():
        raise AuthError("JWXT login page did not contain a CSRF token.")
    return token.strip()


def should_encrypt_password(login_html: str) -> bool:
    """Return whether the login form expects an RSA-encrypted password.

    The page disables encryption only when ``mmsfjm`` is explicitly ``0``. A
    missing field is treated as encryption enabled, matching ``login.js``.
    """

    soup = BeautifulSoup(login_html, "html.parser")
    field = soup.find("input", attrs={"name": "mmsfjm"})
    if field is None:
        return True
    return str(field.get("value", "")).strip() != "0"


def fetch_public_key(client: object) -> tuple[str, str]:
    """Fetch the RSA public key the login form uses to encrypt the password."""

    timestamp_ms = int(time.time() * 1000)
    response = client.get(f"{PUBLIC_KEY_PATH}?time={timestamp_ms}")
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - response library varies.
        raise AuthError("JWXT public key response was not valid JSON.") from exc

    modulus = payload.get("modulus") if isinstance(payload, dict) else None
    exponent = payload.get("exponent") if isinstance(payload, dict) else None
    if not isinstance(modulus, str) or not isinstance(exponent, str):
        raise AuthError("JWXT public key response was incomplete.")
    if not modulus or not exponent:
        raise AuthError("JWXT public key response was incomplete.")
    return modulus, exponent


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

            password = config.cumt.password
            if should_encrypt_password(login_response.text):
                modulus, exponent = fetch_public_key(client)
                password = encrypt_password(password, modulus, exponent)

            response = client.post(
                LOGIN_PATH,
                data={
                    "csrftoken": csrf_token,
                    "language": "zh_CN",
                    "ydType": "",
                    "yhm": config.cumt.username,
                    "mm": password,
                    "yzm": captcha_code,
                },
            )
            if _looks_logged_in(client, response):
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


_LOGIN_FORM_MARKERS = ('name="yhm"', 'name="yzm"', 'name="csrftoken"')
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def _looks_logged_in(client: object, response: object) -> bool:
    status_code = getattr(response, "status_code", None)
    if status_code in _REDIRECT_STATUS_CODES:
        location = _redirect_location(response)
        if location is None:
            return False
        if "login_slogin" not in location:
            return True
        # Some JWXT deployments redirect a successful login back to the login
        # page, which then redirects to the menu. Follow one hop so a genuine
        # failure (login form) is not confused with that success chain.
        return _login_redirect_resolves_to_menu(client, location)

    return _is_non_login_page(response)


def _login_redirect_resolves_to_menu(client: object, location: str) -> bool:
    try:
        follow = client.get(location)
    except Exception:  # noqa: BLE001 - a probe failure is a login failure.
        return False

    if getattr(follow, "status_code", None) in _REDIRECT_STATUS_CODES:
        next_location = _redirect_location(follow)
        return next_location is not None and "login_slogin" not in next_location
    return _is_non_login_page(follow)


def _is_non_login_page(response: object) -> bool:
    html = getattr(response, "text", "")
    if not isinstance(html, str) or not html.strip():
        return False
    return not any(marker in html for marker in _LOGIN_FORM_MARKERS)


def _redirect_location(response: object) -> str | None:
    headers = getattr(response, "headers", None)
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    for name in ("Location", "location"):
        location = getter(name)
        if isinstance(location, str) and location.strip():
            return location.strip()
    return None
