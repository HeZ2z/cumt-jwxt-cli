"""Session orchestrator boundary tests."""

from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.app.session as app_module
from cumt_jwxt_cli.errors import QueryError


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        http=SimpleNamespace(
            timeout_seconds=30,
            retry_attempts=2,
            retry_backoff_seconds=1.5,
        ),
        captcha=SimpleNamespace(
            openai_compatible=SimpleNamespace(),
            manual_timeout_seconds=60,
        ),
    )


def _runtime_state(**overrides: object) -> SimpleNamespace:
    values = {
        "session_cookies": {},
        "session_updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _query_result() -> SimpleNamespace:
    return SimpleNamespace(
        grades=(),
        changes=(),
        state=SimpleNamespace(last_successful_query_at="2026-05-07T12:00:00+08:00"),
    )


def test_query_grades_with_session_reuse_reuses_saved_cookies_without_login(
    monkeypatch,
) -> None:
    previous_state = _runtime_state(
        session_cookies={"JSESSIONID": "saved"},
        session_updated_at="2026-05-08T12:00:00+08:00",
    )
    client_events: list[tuple[str, object]] = []
    login_calls = 0
    run_calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_events.append(("init", kwargs))

        def __enter__(self) -> "FakeClient":
            client_events.append(("enter", None))
            return self

        def __exit__(self, *args: object) -> None:
            client_events.append(("exit", None))

        def load_cookies(self, cookies: dict[str, str] | None) -> None:
            client_events.append(("load_cookies", cookies))

        def check_reachable(self) -> None:
            client_events.append(("check_reachable", None))

        def export_cookies(self) -> dict[str, str]:
            client_events.append(("export_cookies", None))
            return {"JSESSIONID": "saved"}

        def reset_session(self) -> None:
            client_events.append(("reset_session", None))

        def cookies(self) -> dict[str, str]:
            raise AssertionError("legacy cookies() should not be used")

    monkeypatch.setattr(app_module, "load_runtime_state", lambda config: previous_state)
    monkeypatch.setattr(app_module, "JWXTClient", FakeClient)

    def fake_login(config, client) -> None:
        nonlocal login_calls
        login_calls += 1

    def fake_run_grade_query(*args: object, **kwargs: object) -> SimpleNamespace:
        run_calls.append(kwargs)
        return _query_result()

    monkeypatch.setattr(app_module, "_login", fake_login)
    monkeypatch.setattr(app_module, "run_grade_query", fake_run_grade_query)

    result = app_module.query_grades_with_session_reuse(
        _config(),
        force_email=False,
        trust_env=False,
    )

    assert result == _query_result()
    assert login_calls == 0
    assert run_calls == [
        {
            "previous_state": previous_state,
            "session_cookies": {"JSESSIONID": "saved"},
            "session_updated_at": None,
            "force_email": False,
        }
    ]
    assert client_events == [
        (
            "init",
            {
                "timeout_seconds": 30,
                "retry_attempts": 2,
                "retry_backoff_seconds": 1.5,
                "trust_env": False,
            },
        ),
        ("enter", None),
        ("load_cookies", {"JSESSIONID": "saved"}),
        ("check_reachable", None),
        ("export_cookies", None),
        ("exit", None),
    ]


def test_query_grades_with_session_reuse_logs_in_when_no_saved_cookies(
    monkeypatch,
) -> None:
    previous_state = _runtime_state()
    login_calls = 0
    run_calls: list[dict[str, object]] = []
    session_updated_at = "2026-05-09T10:00:00+00:00"

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def load_cookies(self, cookies: dict[str, str] | None) -> None:
            assert cookies == {}

        def check_reachable(self) -> None:
            return None

        def export_cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

        def reset_session(self) -> None:
            raise AssertionError("reset_session should not be needed")

        def cookies(self) -> dict[str, str]:
            raise AssertionError("legacy cookies() should not be used")

    monkeypatch.setattr(app_module, "load_runtime_state", lambda config: previous_state)
    monkeypatch.setattr(app_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(app_module, "_now_iso", lambda: session_updated_at)

    def fake_login(config, client) -> None:
        nonlocal login_calls
        login_calls += 1

    def fake_run_grade_query(*args: object, **kwargs: object) -> SimpleNamespace:
        run_calls.append(kwargs)
        return SimpleNamespace(
            grades=(),
            changes=(),
            state=SimpleNamespace(last_successful_query_at=session_updated_at),
        )

    monkeypatch.setattr(app_module, "_login", fake_login)
    monkeypatch.setattr(app_module, "run_grade_query", fake_run_grade_query)

    result = app_module.query_grades_with_session_reuse(
        _config(),
        force_email=True,
        trust_env=True,
    )

    assert result.state.last_successful_query_at == session_updated_at
    assert login_calls == 1
    assert run_calls == [
        {
            "previous_state": previous_state,
            "session_cookies": {"JSESSIONID": "new"},
            "session_updated_at": session_updated_at,
            "force_email": True,
        }
    ]


def test_query_grades_with_session_reuse_retries_once_after_session_expiry(
    monkeypatch,
) -> None:
    previous_state = _runtime_state(
        session_cookies={"JSESSIONID": "saved"},
        session_updated_at="2026-05-08T12:00:00+08:00",
    )
    login_calls = 0
    run_calls: list[dict[str, object]] = []
    reset_calls = 0

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def load_cookies(self, cookies: dict[str, str] | None) -> None:
            assert cookies == {"JSESSIONID": "saved"}

        def check_reachable(self) -> None:
            return None

        def export_cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "renewed"}

        def reset_session(self) -> None:
            nonlocal reset_calls
            reset_calls += 1

        def cookies(self) -> dict[str, str]:
            raise AssertionError("legacy cookies() should not be used")

    monkeypatch.setattr(app_module, "load_runtime_state", lambda config: previous_state)
    monkeypatch.setattr(app_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(app_module, "_now_iso", lambda: "2026-05-09T10:00:00+00:00")

    def fake_login(config, client) -> None:
        nonlocal login_calls
        login_calls += 1

    def fake_run_grade_query(*args: object, **kwargs: object) -> SimpleNamespace:
        run_calls.append(kwargs)
        if len(run_calls) == 1:
            raise QueryError("JWXT grade list request failed with HTTP 901.")
        return _query_result()

    monkeypatch.setattr(app_module, "_login", fake_login)
    monkeypatch.setattr(app_module, "run_grade_query", fake_run_grade_query)

    result = app_module.query_grades_with_session_reuse(
        _config(),
        force_email=False,
        trust_env=False,
    )

    assert result == _query_result()
    assert login_calls == 1
    assert reset_calls == 1
    assert run_calls == [
        {
            "previous_state": previous_state,
            "session_cookies": {"JSESSIONID": "renewed"},
            "session_updated_at": None,
            "force_email": False,
        },
        {
            "previous_state": previous_state,
            "session_cookies": {"JSESSIONID": "renewed"},
            "session_updated_at": "2026-05-09T10:00:00+00:00",
            "force_email": False,
        },
    ]


def test_query_grades_with_session_reuse_does_not_retry_non_session_error(
    monkeypatch,
) -> None:
    previous_state = _runtime_state(
        session_cookies={"JSESSIONID": "saved"},
        session_updated_at="2026-05-08T12:00:00+08:00",
    )
    login_calls = 0
    run_calls = 0

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def load_cookies(self, cookies: dict[str, str] | None) -> None:
            assert cookies == {"JSESSIONID": "saved"}

        def check_reachable(self) -> None:
            return None

        def export_cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "saved"}

        def reset_session(self) -> None:
            raise AssertionError("reset_session should not be used")

        def cookies(self) -> dict[str, str]:
            raise AssertionError("legacy cookies() should not be used")

    monkeypatch.setattr(app_module, "load_runtime_state", lambda config: previous_state)
    monkeypatch.setattr(app_module, "JWXTClient", FakeClient)

    def fake_login(config, client) -> None:
        nonlocal login_calls
        login_calls += 1

    def fake_run_grade_query(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal run_calls
        run_calls += 1
        raise QueryError("JWXT request failed after retry attempts.")

    monkeypatch.setattr(app_module, "_login", fake_login)
    monkeypatch.setattr(app_module, "run_grade_query", fake_run_grade_query)

    with pytest.raises(QueryError, match="retry attempts"):
        app_module.query_grades_with_session_reuse(
            _config(),
            force_email=False,
            trust_env=True,
        )

    assert login_calls == 0
    assert run_calls == 1
