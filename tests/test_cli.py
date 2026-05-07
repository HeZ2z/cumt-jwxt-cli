"""CLI parser tests."""

import json
from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.cli as cli_module
from cumt_jwxt_cli.cli import build_parser, main
from cumt_jwxt_cli.errors import ExitCode


def _runtime_state(**overrides: object) -> SimpleNamespace:
    values = {
        "schema_version": 2,
        "session_cookies": {},
        "session_updated_at": None,
        "last_grade_snapshot": (),
        "last_successful_query_at": None,
        "last_notified_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _empty_query_result() -> SimpleNamespace:
    return SimpleNamespace(
        grades=(),
        changes=(),
        state=SimpleNamespace(last_successful_query_at="2026-05-07T12:00:00+08:00"),
    )


def test_build_parser_parses_grades_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["grades", "query"])

    assert args.command == "grades"
    assert args.grades_command == "query"


def test_grades_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "grades",
            "query",
            "--config",
            "config.test.json",
            "--year",
            "2025",
            "--semester",
            "3",
            "--force-email",
            "--no-proxy",
            "--no-interactive",
            "--save-json",
            "--save-report",
            "--output-dir",
            "./out",
            "--verbose",
        ]
    )

    assert args.config == "config.test.json"
    assert args.year == "2025"
    assert args.semester == "3"
    assert args.force_email is True
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.save_json is True
    assert args.save_report is True
    assert args.output_dir == "./out"
    assert args.verbose is True


def test_main_shows_help_for_grades_command(capsys) -> None:
    exit_code = main(["grades"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "usage: cumt-jwxt grades" in captured.out
    assert captured.err == ""


def test_main_returns_config_error_for_missing_config(capsys, tmp_path) -> None:
    config_path = tmp_path / "missing.json"

    exit_code = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.CONFIG_ERROR)
    assert captured.out == ""
    assert "Configuration file not found" in captured.err


def test_main_runs_grades_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
                "notify": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(),
    )
    monkeypatch.setattr(
        cli_module,
        "login",
        lambda config, client, recognize_captcha: {},
    )
    monkeypatch.setattr(
        cli_module,
        "run_grade_query",
        lambda *args, **kwargs: _empty_query_result(),
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT grades 2024-12" in captured.out
    assert captured.err == ""


def test_main_uses_proxy_by_default(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    created_clients: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            created_clients.append(kwargs)

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(),
    )
    monkeypatch.setattr(
        cli_module,
        "login",
        lambda config, client, recognize_captcha: {},
    )
    monkeypatch.setattr(
        cli_module,
        "run_grade_query",
        lambda *args, **kwargs: _empty_query_result(),
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert created_clients[0]["trust_env"] is True


def test_main_disables_proxy_when_no_proxy_flag_is_set(
    capsys,
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    created_clients: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            created_clients.append(kwargs)

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(),
    )
    monkeypatch.setattr(
        cli_module,
        "login",
        lambda config, client, recognize_captcha: {},
    )
    monkeypatch.setattr(
        cli_module,
        "run_grade_query",
        lambda *args, **kwargs: _empty_query_result(),
    )

    exit_code = main(["grades", "query", "--config", str(config_path), "--no-proxy"])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert created_clients[0]["trust_env"] is False


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
        (cli_module.NotifyError("notify"), ExitCode.NOTIFY_ERROR),
    ],
)
def test_main_maps_runtime_errors_to_exit_codes(
    capsys,
    tmp_path,
    monkeypatch,
    raised: Exception,
    expected_code: ExitCode,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(),
    )
    monkeypatch.setattr(
        cli_module,
        "login",
        lambda config, client, recognize_captcha: {},
    )
    def raise_runtime_error(*args: object, **kwargs: object) -> None:
        raise raised

    monkeypatch.setattr(cli_module, "run_grade_query", raise_runtime_error)

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


def test_main_skips_login_when_saved_session_query_succeeds(
    capsys,
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    login_calls = 0

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "saved"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(
            session_cookies={"JSESSIONID": "saved"},
            session_updated_at="2026-05-07T12:00:00+08:00",
        ),
    )

    def fake_login(config, client, recognize_captcha) -> None:
        nonlocal login_calls
        login_calls += 1

    monkeypatch.setattr(cli_module, "login", fake_login)
    monkeypatch.setattr(
        cli_module,
        "run_grade_query",
        lambda *args, **kwargs: _empty_query_result(),
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert login_calls == 0


def test_main_retries_with_login_when_saved_session_looks_expired(
    capsys,
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2024", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    login_calls = 0
    query_calls = 0

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def check_reachable(self) -> None:
            return None

        def cookies(self) -> dict[str, str]:
            return {"JSESSIONID": "new"}

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli_module, "JWXTClient", FakeClient)
    monkeypatch.setattr(
        cli_module,
        "load_runtime_state",
        lambda config: _runtime_state(
            session_cookies={"JSESSIONID": "saved"},
            session_updated_at="2026-05-07T12:00:00+08:00",
        ),
    )

    def fake_login(config, client, recognize_captcha) -> None:
        nonlocal login_calls
        login_calls += 1

    def fake_run_grade_query(
        *args: object,
        **kwargs: object,
    ):
        nonlocal query_calls
        query_calls += 1
        if query_calls == 1:
            raise cli_module.QueryError("JWXT grade list request failed with HTTP 901.")
        return SimpleNamespace(
            grades=(),
            changes=(),
            state=SimpleNamespace(last_successful_query_at="2026-05-07T12:00:00+08:00"),
        )

    monkeypatch.setattr(cli_module, "login", fake_login)
    monkeypatch.setattr(cli_module, "run_grade_query", fake_run_grade_query)

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert login_calls == 1
    assert query_calls == 2
