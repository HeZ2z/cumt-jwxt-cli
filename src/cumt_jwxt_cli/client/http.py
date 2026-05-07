"""HTTP client wrapper for JWXT requests."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from cumt_jwxt_cli.errors import QueryError

BASE_URL = "http://jwxt.cumt.edu.cn/jwglxt"
USER_AGENT = "cumt-jwxt-cli/0.1"


class JWXTClient:
    """Small synchronous httpx wrapper with bounded retries."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        retry_attempts: int,
        retry_backoff_seconds: float,
        cookies: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = True,
    ) -> None:
        self._retry_attempts = max(0, retry_attempts)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout_seconds,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/html, */*",
            },
            cookies=dict(cookies or {}),
            transport=transport,
            follow_redirects=False,
            trust_env=trust_env,
        )

    def __enter__(self) -> JWXTClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""

        self._client.close()

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request with retry handling."""

        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request with retry handling."""

        return self._request("POST", path, **kwargs)

    def cookies(self) -> dict[str, str]:
        """Return a serializable cookie snapshot."""

        snapshot: dict[str, str] = {}
        for cookie in self._client.cookies.jar:
            snapshot[cookie.name] = cookie.value
        return snapshot

    def clear_cookies(self) -> None:
        """Drop all cookies before forcing a fresh login."""

        self._client.cookies.clear()

    def check_reachable(self) -> None:
        """Fail fast when the JWXT host cannot be reached with this client."""

        try:
            self._client.get("/")
        except httpx.TimeoutException as exc:
            raise QueryError(
                "JWXT network check timed out. Check network or proxy settings."
            ) from exc
        except httpx.RequestError as exc:
            raise QueryError(
                "JWXT network check failed. Check network or proxy settings."
            ) from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempts = self._retry_attempts + 1
        last_error: httpx.HTTPError | None = None

        for attempt_index in range(attempts):
            try:
                response = self._client.request(method, path, **kwargs)
                if response.status_code >= 400:
                    response.raise_for_status()
                return response
            except httpx.RequestError as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                if 500 <= exc.response.status_code < 600:
                    last_error = exc
                else:
                    raise QueryError(
                        f"JWXT request failed with HTTP {exc.response.status_code}."
                    ) from exc

            if attempt_index < attempts - 1 and self._retry_backoff_seconds:
                time.sleep(self._retry_backoff_seconds * (attempt_index + 1))

        raise QueryError("JWXT request failed after retry attempts.") from last_error
