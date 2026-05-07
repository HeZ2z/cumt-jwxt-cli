"""HTTP client boundary tests."""

import httpx
import pytest

from cumt_jwxt_cli.client.http import JWXTClient
from cumt_jwxt_cli.errors import QueryError


def test_jwxt_client_sets_timeout_headers_and_cookies() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=0,
        retry_backoff_seconds=0,
        transport=transport,
        cookies={"route": "abc"},
    ) as client:
        response = client.get("/xtgl/login_slogin.html")

    assert response.json() == {"ok": True}
    assert requests[0].url == "http://jwxt.cumt.edu.cn/jwglxt/xtgl/login_slogin.html"
    assert requests[0].headers["user-agent"].startswith("cumt-jwxt-cli/")
    assert requests[0].headers["cookie"] == "route=abc"


def test_jwxt_client_accepts_explicit_trust_env_false() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True})
    )

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=0,
        retry_backoff_seconds=0,
        transport=transport,
        trust_env=False,
    ) as client:
        assert client.get("/status").json() == {"ok": True}


def test_jwxt_client_check_reachable_uses_base_jwxt_path() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=0,
        retry_backoff_seconds=0,
        transport=transport,
    ) as client:
        client.check_reachable()

    assert requests[0].url == "http://jwxt.cumt.edu.cn/jwglxt/"


def test_jwxt_client_check_reachable_reports_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=0,
        retry_backoff_seconds=0,
        transport=transport,
    ) as client:
        with pytest.raises(QueryError, match="network check timed out"):
            client.check_reachable()


def test_jwxt_client_retries_transient_request_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary failure", request=request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=1,
        retry_backoff_seconds=0,
        transport=transport,
    ) as client:
        assert client.get("/status").json() == {"ok": True}

    assert attempts == 2


def test_jwxt_client_allows_redirect_responses() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(302))

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=0,
        retry_backoff_seconds=0,
        transport=transport,
    ) as client:
        response = client.post("/xtgl/login_slogin.html", data={})

    assert response.status_code == 302


def test_jwxt_client_wraps_network_errors_after_retry_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("still failing", request=request)

    transport = httpx.MockTransport(handler)

    with JWXTClient(
        timeout_seconds=5,
        retry_attempts=1,
        retry_backoff_seconds=0,
        transport=transport,
    ) as client:
        with pytest.raises(QueryError, match="JWXT request failed"):
            client.get("/status")
