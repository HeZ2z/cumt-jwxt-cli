"""CLI parser tests."""

import json
from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.cli as cli_module
from cumt_jwxt_cli.cli import build_parser, main
from cumt_jwxt_cli.errors import ExitCode
from cumt_jwxt_cli.models import GradeQueryScope, PerScopeState


def _empty_query_result() -> SimpleNamespace:
    return SimpleNamespace(
        grades=(),
        changes=(),
        state=SimpleNamespace(
            grade_queries={
                GradeQueryScope(year="2024", semester="12"): PerScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-05-07T12:00:00+08:00",
                    last_notified_at=None,
                )
            }
        ),
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

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        lambda config, *, force_email, trust_env: _empty_query_result(),
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT 成绩报告 2024-2025学年 第二学期" in captured.out
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
    orchestrator_calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query_grades_with_session_reuse(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
    ) -> SimpleNamespace:
        orchestrator_calls.append(
            {
                "config": config,
                "force_email": force_email,
                "trust_env": trust_env,
            }
        )
        return _empty_query_result()

    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        fake_query_grades_with_session_reuse,
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert orchestrator_calls[0]["trust_env"] is True
    assert orchestrator_calls[0]["force_email"] is False


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
    orchestrator_calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query_grades_with_session_reuse(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
    ) -> SimpleNamespace:
        orchestrator_calls.append(
            {
                "config": config,
                "force_email": force_email,
                "trust_env": trust_env,
            }
        )
        return _empty_query_result()

    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        fake_query_grades_with_session_reuse,
    )

    exit_code = main(["grades", "query", "--config", str(config_path), "--no-proxy"])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert orchestrator_calls[0]["trust_env"] is False


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

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
    ) -> None:
        raise raised

    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        raise_runtime_error,
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err
