"""CLI parser tests."""

import json
from collections.abc import Callable
from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.cli as cli_module
from cumt_jwxt_cli.classrooms.query_fetch import ClassroomQueryResult
from cumt_jwxt_cli.cli import build_parser, main
from cumt_jwxt_cli.courses.query_fetch import CourseQueryResult
from cumt_jwxt_cli.errors import ExitCode
from cumt_jwxt_cli.models import (
    AcademicOverview,
    AcademicSummaryResult,
    ExamInfo,
    ExamScopeState,
    GradeQueryScope,
    PeriodTime,
    PerScopeState,
    RuntimeState,
    ScheduleLesson,
    ScheduleScopeState,
    ScheduleSlot,
    TeachingPlanCourse,
    TeachingPlanHeader,
    TeachingPlanResult,
)
from cumt_jwxt_cli.state import state_lock


def _empty_query_result() -> SimpleNamespace:
    return SimpleNamespace(
        grades=(),
        changes=(),
        year="2024",
        semester="12",
        state=SimpleNamespace(
            grade_queries={
                GradeQueryScope(year="2024", semester="12"): PerScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-05-07T12:00:00+08:00",
                    last_notified_at=None,
                )
            },
            exam_queries={},
        ),
    )


def _empty_exam_query_result() -> SimpleNamespace:
    return SimpleNamespace(
        exams=(),
        changes=(),
        year="2025",
        semester="12",
        state=RuntimeState(
            schema_version=5,
            session_cookies={},
            session_updated_at=None,
            grade_queries={},
            exam_queries={
                GradeQueryScope(year="2025", semester="12"): ExamScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-06-01T12:00:00+08:00",
                    last_notified_at=None,
                )
            },
        ),
    )


def _empty_schedule_query_result() -> SimpleNamespace:
    return SimpleNamespace(
        lessons=(),
        changes=(),
        period_times=(),
        year="2025",
        semester="12",
        state=RuntimeState(
            schema_version=5,
            session_cookies={},
            session_updated_at=None,
            grade_queries={},
            exam_queries={},
            schedule_queries={
                GradeQueryScope(year="2025", semester="12"): ScheduleScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-06-01T12:00:00+08:00",
                    last_notified_at=None,
                )
            },
        ),
    )


def _sample_exams() -> tuple[ExamInfo, ...]:
    return (
        ExamInfo(
            course_code="M08209",
            course_name="嵌入式系统设计与应用",
            exam_time="2026-05-06(16:15-17:55)",
            location="博2-B102",
            campus="南湖校区",
            exam_name="2025-2026-2课程考试",
            exam_method="考试",
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
    assert "用法: cumt-jwxt grades" in captured.out
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
        lambda config, *, force_email, trust_env, allow_manual_captcha: (
            _empty_query_result()
        ),
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT 成绩报告 2024-2025学年 第二学期" in captured.out
    assert captured.err == ""


def test_main_uses_result_scope_for_grades_output(
    capsys, tmp_path, monkeypatch
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
    result = SimpleNamespace(
        grades=(),
        changes=(),
        year="2025",
        semester="3",
        state=SimpleNamespace(
            grade_queries={
                GradeQueryScope(year="2025", semester="3"): PerScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-05-07T12:00:00+08:00",
                    last_notified_at=None,
                )
            }
        ),
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        lambda config, *, force_email, trust_env, allow_manual_captcha: result,
    )

    exit_code = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == int(ExitCode.OK)
    assert "CUMT 成绩报告 2025-2026学年 第一学期" in captured.out


def test_main_fails_fast_when_state_file_is_locked(
    capsys, tmp_path, monkeypatch
) -> None:
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
    calls: list[int] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_grades_with_session_reuse",
        lambda *args, **kwargs: (calls.append(1), _empty_query_result())[1],
    )

    with state_lock(SimpleNamespace(config_path=config_path)):
        locked_exit = main(["grades", "query", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert locked_exit == int(ExitCode.UNKNOWN)
    assert calls == []
    assert "already using this state file" in captured.err

    # The lock is released once the first run exits.
    assert main(["grades", "query", "--config", str(config_path)]) == int(ExitCode.OK)
    assert calls == [1]


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
        allow_manual_captcha: bool,
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
        allow_manual_captcha: bool,
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
        allow_manual_captcha: bool,
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


# -- exams ----------------------------------------------------------------


def test_build_parser_parses_exams_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["exams", "query"])

    assert args.command == "exams"
    assert args.exams_command == "query"


def test_exams_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "exams",
            "query",
            "--config",
            "config.test.json",
            "--year",
            "2025",
            "--semester",
            "12",
            "--force-email",
            "--no-proxy",
            "--no-interactive",
            "--save-json",
            "--save-report",
            "--save-ics",
            "--output-dir",
            "./out",
            "--verbose",
        ]
    )

    assert args.config == "config.test.json"
    assert args.year == "2025"
    assert args.semester == "12"
    assert args.force_email is True
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.save_json is True
    assert args.save_report is True
    assert args.save_ics is True
    assert args.output_dir == "./out"
    assert args.verbose is True


def test_main_shows_help_for_exams_command(capsys) -> None:
    exit_code = main(["exams"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt exams" in captured.out
    assert captured.err == ""


def test_main_runs_exams_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
                "notify": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_exams_with_session_reuse",
        lambda config, *, force_email, trust_env, allow_manual_captcha: (
            _empty_exam_query_result()
        ),
    )

    exit_code = main(["exams", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT exams 2025-2026 第二学期" in captured.out
    assert captured.err == ""


def test_exams_query_no_proxy(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query_exams(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
        allow_manual_captcha: bool,
    ) -> SimpleNamespace:
        calls.append({"force_email": force_email, "trust_env": trust_env})
        return _empty_exam_query_result()

    monkeypatch.setattr(
        cli_module,
        "query_exams_with_session_reuse",
        fake_query_exams,
    )

    main(["exams", "query", "--config", str(config_path), "--no-proxy"])

    assert calls == [{"force_email": False, "trust_env": False}]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
        (cli_module.NotifyError("notify"), ExitCode.NOTIFY_ERROR),
        (cli_module.StateError("state"), ExitCode.UNKNOWN),
        (cli_module.SnapshotError("snapshot"), ExitCode.UNKNOWN),
    ],
)
def test_exams_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "12"},
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
        allow_manual_captcha: bool,
    ) -> None:
        raise raised

    monkeypatch.setattr(
        cli_module,
        "query_exams_with_session_reuse",
        raise_runtime_error,
    )

    exit_code = main(["exams", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


# -- schedule -------------------------------------------------------------


def test_build_parser_parses_schedule_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["schedule", "query"])

    assert args.command == "schedule"
    assert args.schedule_command == "query"


def test_schedule_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "schedule",
            "query",
            "--config",
            "config.test.json",
            "--year",
            "2025",
            "--semester",
            "12",
            "--force-email",
            "--no-proxy",
            "--no-interactive",
            "--save-json",
            "--save-report",
            "--save-ics",
            "--output-dir",
            "./out",
            "--verbose",
        ]
    )

    assert args.config == "config.test.json"
    assert args.year == "2025"
    assert args.semester == "12"
    assert args.force_email is True
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.save_json is True
    assert args.save_report is True
    assert args.save_ics is True
    assert args.output_dir == "./out"
    assert args.verbose is True


def test_main_shows_help_for_schedule_command(capsys) -> None:
    exit_code = main(["schedule"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt schedule" in captured.out
    assert captured.err == ""


def test_main_runs_schedule_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
                "notify": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_schedule_with_session_reuse",
        lambda config, *, force_email, trust_env, allow_manual_captcha: (
            _empty_schedule_query_result()
        ),
    )

    exit_code = main(["schedule", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT 课表 2025-2026 第二学期" in captured.out
    assert captured.err == ""


def test_main_schedule_query_includes_clock_times(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
                "notify": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    lesson = ScheduleLesson(
        course_code="A001",
        course_name="高等数学",
        teaching_class=None,
        teacher=None,
        credits=None,
        course_type=None,
        slots=(
            ScheduleSlot(weekday=1, periods="1-2", weeks=(1,), location="教一A101"),
        ),
    )
    result = SimpleNamespace(
        lessons=(lesson,),
        changes=(),
        period_times=(
            PeriodTime(period="1", start="08:00", end="08:50"),
            PeriodTime(period="2", start="08:55", end="09:45"),
        ),
        year="2025",
        semester="12",
        state=RuntimeState(
            schema_version=5,
            session_cookies={},
            session_updated_at=None,
            grade_queries={},
            exam_queries={},
            schedule_queries={
                GradeQueryScope(year="2025", semester="12"): ScheduleScopeState(
                    snapshot=(),
                    last_successful_query_at="2026-06-01T12:00:00+08:00",
                    last_notified_at=None,
                )
            },
        ),
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_schedule_with_session_reuse",
        lambda config, *, force_email, trust_env, allow_manual_captcha: result,
    )

    exit_code = main(["schedule", "query", "--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "周一 1-2节 08:00-09:45 第1周 教一A101" in captured.out


def test_schedule_query_no_proxy(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query_schedule(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
        allow_manual_captcha: bool,
    ) -> SimpleNamespace:
        calls.append({"force_email": force_email, "trust_env": trust_env})
        return _empty_schedule_query_result()

    monkeypatch.setattr(
        cli_module,
        "query_schedule_with_session_reuse",
        fake_query_schedule,
    )

    main(["schedule", "query", "--config", str(config_path), "--no-proxy"])

    assert calls == [{"force_email": False, "trust_env": False}]


@pytest.mark.parametrize(
    ("argv", "orchestration_name", "empty_result"),
    [
        (["grades", "query"], "query_grades_with_session_reuse", _empty_query_result),
        (
            ["exams", "query"],
            "query_exams_with_session_reuse",
            _empty_exam_query_result,
        ),
        (
            ["schedule", "query"],
            "query_schedule_with_session_reuse",
            _empty_schedule_query_result,
        ),
    ],
)
def test_main_disables_manual_captcha_when_no_interactive(
    capsys,
    tmp_path,
    monkeypatch,
    argv: list[str],
    orchestration_name: str,
    empty_result: Callable[[], SimpleNamespace],
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[bool] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(
        config: object,
        *,
        force_email: bool,
        trust_env: bool,
        allow_manual_captcha: bool,
    ) -> SimpleNamespace:
        calls.append(allow_manual_captcha)
        return empty_result()

    monkeypatch.setattr(cli_module, orchestration_name, fake_query)

    exit_code = main([*argv, "--config", str(config_path), "--no-interactive"])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert calls == [False]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
        (cli_module.NotifyError("notify"), ExitCode.NOTIFY_ERROR),
        (cli_module.StateError("state"), ExitCode.UNKNOWN),
        (cli_module.SnapshotError("snapshot"), ExitCode.UNKNOWN),
    ],
)
def test_schedule_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "12"},
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
        allow_manual_captcha: bool,
    ) -> None:
        raise raised

    monkeypatch.setattr(
        cli_module,
        "query_schedule_with_session_reuse",
        raise_runtime_error,
    )

    exit_code = main(["schedule", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


# -- classrooms -----------------------------------------------------------


def test_build_parser_parses_classrooms_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["classrooms", "query", "--date", "2026-11-23"])

    assert args.command == "classrooms"
    assert args.classrooms_command == "query"
    assert args.date == "2026-11-23"
    assert args.campus == "all"
    assert args.limit == 50


def test_classrooms_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "classrooms",
            "query",
            "--date",
            "2026-11-23",
            "--start",
            "08:00",
            "--end",
            "09:40",
            "--campus",
            "nanhu",
            "--building",
            "博1",
            "--min-seats",
            "50",
            "--max-seats",
            "100",
            "--lendable",
            "--limit",
            "0",
            "--year",
            "2026",
            "--semester",
            "3",
            "--config",
            "config.test.json",
            "--no-proxy",
            "--no-interactive",
            "--verbose",
        ]
    )

    assert args.start == "08:00"
    assert args.end == "09:40"
    assert args.campus == "nanhu"
    assert args.building == "博1"
    assert args.min_seats == 50
    assert args.max_seats == 100
    assert args.lendable is True
    assert args.limit == 0
    assert args.year == "2026"
    assert args.semester == "3"
    assert args.config == "config.test.json"
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.verbose is True


def test_main_shows_help_for_classrooms_command(capsys) -> None:
    exit_code = main(["classrooms"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt classrooms" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["classrooms", "query"],
        ["classrooms", "query", "--date", "2026/11/23"],
        ["classrooms", "query", "--date", "2026-11-23", "--start", "08:00"],
        ["classrooms", "query", "--date", "2026-11-23", "--start", "8:00"],
        ["classrooms", "query", "--date", "2026-11-23", "--limit", "-1"],
    ],
)
def test_classrooms_query_rejects_invalid_arguments(capsys, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err != ""


def test_main_runs_classrooms_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "3"},
                "notify": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, options, trust_env, allow_manual_captcha):
        calls.append(
            {
                "config": config,
                "options": options,
                "trust_env": trust_env,
                "allow_manual_captcha": allow_manual_captcha,
            }
        )
        return ClassroomQueryResult(classrooms=(), total=0)

    monkeypatch.setattr(cli_module, "query_classrooms_with_session_reuse", fake_query)

    exit_code = main(
        [
            "classrooms",
            "query",
            "--config",
            str(config_path),
            "--date",
            "2026-11-23",
            "--start",
            "08:00",
            "--end",
            "09:40",
            "--campus",
            "nanhu",
            "--building",
            "博1",
            "--min-seats",
            "50",
            "--max-seats",
            "100",
            "--lendable",
            "--limit",
            "5",
            "--year",
            "2026",
            "--semester",
            "3",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 空闲教室 2026-11-23 08:00-09:40（南湖校区）" in captured.out
    assert "未找到符合条件的空闲教室。" in captured.out

    assert len(calls) == 1
    options = calls[0]["options"]
    assert options.date == "2026-11-23"
    assert options.start == "08:00"
    assert options.end == "09:40"
    assert options.campus == "nanhu"
    assert options.building == "博1"
    assert options.min_seats == 50
    assert options.max_seats == 100
    assert options.lendable is True
    assert options.limit == 5
    assert calls[0]["trust_env"] is True
    assert calls[0]["allow_manual_captcha"] is True
    config = calls[0]["config"]
    assert config.query.year == "2026"
    assert config.query.semester == "3"


def test_classrooms_query_no_proxy_and_no_interactive(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "3"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, options, trust_env, allow_manual_captcha):
        calls.append(
            {"trust_env": trust_env, "allow_manual_captcha": allow_manual_captcha}
        )
        return ClassroomQueryResult(classrooms=(), total=0)

    monkeypatch.setattr(cli_module, "query_classrooms_with_session_reuse", fake_query)

    main(
        [
            "classrooms",
            "query",
            "--config",
            str(config_path),
            "--date",
            "2026-11-23",
            "--no-proxy",
            "--no-interactive",
        ]
    )

    assert calls == [{"trust_env": False, "allow_manual_captcha": False}]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
    ],
)
def test_classrooms_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "3"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(config, *, options, trust_env, allow_manual_captcha):
        raise raised

    monkeypatch.setattr(
        cli_module, "query_classrooms_with_session_reuse", raise_runtime_error
    )

    exit_code = main(
        [
            "classrooms",
            "query",
            "--config",
            str(config_path),
            "--date",
            "2026-11-23",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


# -- academic -------------------------------------------------------------


def _empty_academic_result() -> AcademicSummaryResult:
    return AcademicSummaryResult(
        overview=AcademicOverview(
            snapshot_at="2026-11-21 08:30",
            gpa_all="3.2",
            gpa_degree="3.0",
            plan_total="108",
            plan_passed="75",
            plan_failed="0",
            plan_unlearned="29",
            plan_in_progress="4",
            out_of_plan_passed="9",
            out_of_plan_failed="2",
        ),
        plan_nodes=(),
        property_stats=(),
    )


def test_build_parser_parses_academic_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["academic", "query"])

    assert args.command == "academic"
    assert args.academic_command == "query"


def test_academic_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "academic",
            "query",
            "--config",
            "config.test.json",
            "--no-proxy",
            "--no-interactive",
            "--verbose",
        ]
    )

    assert args.config == "config.test.json"
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.verbose is True


@pytest.mark.parametrize(
    "argv",
    [
        ["academic", "query", "--year", "2025"],
        ["academic", "query", "--semester", "12"],
        ["academic", "query", "--save-json"],
        ["academic", "query", "--save-report"],
        ["academic", "query", "--force-email"],
    ],
)
def test_academic_query_rejects_unsupported_arguments(capsys, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err != ""


def test_main_shows_help_for_academic_command(capsys) -> None:
    exit_code = main(["academic"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt academic" in captured.out
    assert captured.err == ""


def test_main_runs_academic_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, trust_env, allow_manual_captcha):
        calls.append(
            {
                "trust_env": trust_env,
                "allow_manual_captcha": allow_manual_captcha,
                "year": config.query.year,
                "semester": config.query.semester,
            }
        )
        return _empty_academic_result()

    monkeypatch.setattr(cli_module, "query_academic_with_session_reuse", fake_query)

    exit_code = main(["academic", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 学业情况（统计时间：2026-11-21 08:30）" in captured.out
    assert calls == [
        {
            "trust_env": True,
            "allow_manual_captcha": True,
            "year": "2025",
            "semester": "12",
        }
    ]


def test_academic_query_no_proxy_and_no_interactive(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, trust_env, allow_manual_captcha):
        calls.append(
            {"trust_env": trust_env, "allow_manual_captcha": allow_manual_captcha}
        )
        return _empty_academic_result()

    monkeypatch.setattr(cli_module, "query_academic_with_session_reuse", fake_query)

    main(
        [
            "academic",
            "query",
            "--config",
            str(config_path),
            "--no-proxy",
            "--no-interactive",
        ]
    )

    assert calls == [{"trust_env": False, "allow_manual_captcha": False}]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
    ],
)
def test_academic_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(config, *, trust_env, allow_manual_captcha):
        raise raised

    monkeypatch.setattr(
        cli_module, "query_academic_with_session_reuse", raise_runtime_error
    )

    exit_code = main(["academic", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


# -- courses --------------------------------------------------------------


def test_build_parser_parses_courses_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["courses", "query", "--teacher", "张三"])

    assert args.command == "courses"
    assert args.courses_command == "query"
    assert args.teacher == "张三"
    assert args.course is None
    assert args.room is None
    assert args.weekday is None
    assert args.periods is None
    assert args.weeks is None
    assert args.limit == 50


def test_courses_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "courses",
            "query",
            "--course",
            "M12345",
            "--teacher",
            "张三",
            "--room",
            "博1-A203",
            "--weekday",
            "3",
            "--periods",
            "1-2",
            "--weeks",
            "1",
            "--limit",
            "10",
            "--year",
            "2026",
            "--semester",
            "3",
            "--config",
            "config.test.json",
            "--no-proxy",
            "--no-interactive",
            "--verbose",
        ]
    )

    assert args.course == "M12345"
    assert args.teacher == "张三"
    assert args.room == "博1-A203"
    assert args.weekday == 3
    assert args.periods == "1-2"
    assert args.weeks == "1"
    assert args.limit == 10
    assert args.year == "2026"
    assert args.semester == "3"
    assert args.config == "config.test.json"
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.verbose is True


def test_main_shows_help_for_courses_command(capsys) -> None:
    exit_code = main(["courses"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt courses" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["courses", "query"],
        ["courses", "query", "--teacher", "张三", "--weekday", "0"],
        ["courses", "query", "--teacher", "张三", "--weekday", "8"],
        ["courses", "query", "--teacher", "张三", "--periods", "abc"],
        ["courses", "query", "--teacher", "张三", "--limit", "-1"],
        ["courses", "query", "--teacher", "张三", "--limit", "1001"],
    ],
)
def test_courses_query_rejects_invalid_arguments(capsys, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err != ""


def test_main_runs_courses_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "3"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, options, trust_env, allow_manual_captcha):
        calls.append(
            {
                "config": config,
                "options": options,
                "trust_env": trust_env,
                "allow_manual_captcha": allow_manual_captcha,
            }
        )
        return CourseQueryResult(sessions=(), total=0, year="2026", semester="3")

    monkeypatch.setattr(cli_module, "query_courses_with_session_reuse", fake_query)

    exit_code = main(
        [
            "courses",
            "query",
            "--config",
            str(config_path),
            "--teacher",
            "张三",
            "--weekday",
            "3",
            "--periods",
            "1-2",
            "--weeks",
            "1",
            "--limit",
            "10",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 上课情况 2026-2027 第一学期" in captured.out
    assert "条件：教师=张三，星期=周三，节次=1-2，起始周=1" in captured.out
    assert "未找到符合条件的上课记录。" in captured.out

    assert len(calls) == 1
    options = calls[0]["options"]
    assert options.course is None
    assert options.teacher == "张三"
    assert options.room is None
    assert options.weekday == 3
    assert options.periods == "1-2"
    assert options.weeks == "1"
    assert options.limit == 10
    assert calls[0]["trust_env"] is True
    assert calls[0]["allow_manual_captcha"] is True
    config = calls[0]["config"]
    assert config.query.year == "2025"
    assert config.query.semester == "3"


def test_courses_query_no_proxy_and_no_interactive(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "3"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, options, trust_env, allow_manual_captcha):
        calls.append(
            {"trust_env": trust_env, "allow_manual_captcha": allow_manual_captcha}
        )
        return CourseQueryResult(sessions=(), total=0, year="2025", semester="3")

    monkeypatch.setattr(cli_module, "query_courses_with_session_reuse", fake_query)

    main(
        [
            "courses",
            "query",
            "--config",
            str(config_path),
            "--course",
            "M12345",
            "--no-proxy",
            "--no-interactive",
        ]
    )

    assert calls == [{"trust_env": False, "allow_manual_captcha": False}]


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
    ],
)
def test_courses_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "3"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(config, *, options, trust_env, allow_manual_captcha):
        raise raised

    monkeypatch.setattr(
        cli_module, "query_courses_with_session_reuse", raise_runtime_error
    )

    exit_code = main(
        [
            "courses",
            "query",
            "--config",
            str(config_path),
            "--teacher",
            "张三",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err


# -- plan -----------------------------------------------------------------


def _plan_result() -> TeachingPlanResult:
    return TeachingPlanResult(
        header=TeachingPlanHeader(
            plan_id="PLAN-1",
            grade="2023",
            major_code="0810",
            major_name="计算机科学与技术",
            college_id="08",
            campus="南湖校区",
            program_length="4",
            course_count="112",
            total_credits="171.0",
        ),
        courses=(
            TeachingPlanCourse(
                course_code="M1",
                course_name="高等数学",
                course_name_en=None,
                credits="5.0",
                total_hours="80",
                study_year="2023",
                study_term="3",
                allowed_terms=None,
                category_name="通识必修",
                class_category=None,
                assessment_method="考试",
                exam_method="考试",
                department="数学学院",
                week_range=None,
                study_type="zx",
                status="0",
            ),
        ),
        total=1,
    )


def test_build_parser_parses_plan_query() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "plan",
            "query",
            "--grade",
            "2023",
            "--college",
            "08",
            "--major",
            "0810",
            "--plan-id",
            "PLAN-1",
            "--list",
            "--course",
            "数学",
            "--study-year",
            "2023",
            "--study-term",
            "2",
            "--type",
            "zx",
            "--config",
            "config.test.json",
            "--no-proxy",
            "--no-interactive",
            "--verbose",
        ]
    )

    assert args.command == "plan"
    assert args.plan_command == "query"
    assert args.grade == "2023"
    assert args.college == "08"
    assert args.major == "0810"
    assert args.plan_id == "PLAN-1"
    assert args.list_only is True
    assert args.course == "数学"
    assert args.study_year == "2023"
    # The CLI maps 1/2/3 to JWXT's 3/12/16.
    assert args.study_term == "12"
    assert args.study_type == "zx"
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.verbose is True


@pytest.mark.parametrize(
    "argv",
    [
        ["plan", "query", "--grade", "2023", "--study-term", "4"],
        ["plan", "query", "--grade", "2023", "--type", "other"],
        ["plan", "query", "--grade", "2023", "--year", "2025"],
        ["plan", "query", "--grade", "2023", "--semester", "12"],
        ["plan", "query", "--grade", "2023", "--save-json"],
        ["plan", "query", "--grade", "2023", "--force-email"],
    ],
)
def test_plan_query_rejects_invalid_arguments(capsys, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err != ""


def test_plan_query_requires_lookup_filter(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["plan", "query", "--list"])

    assert excinfo.value.code == 2
    assert "--plan-id" in capsys.readouterr().err


def test_main_shows_help_for_plan_command(capsys) -> None:
    exit_code = main(["plan"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt plan" in captured.out
    assert captured.err == ""


def test_main_runs_plan_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, filters, trust_env, allow_manual_captcha):
        calls.append(
            {
                "filters": filters,
                "trust_env": trust_env,
                "allow_manual_captcha": allow_manual_captcha,
            }
        )
        return _plan_result()

    monkeypatch.setattr(cli_module, "query_plan_with_session_reuse", fake_query)

    exit_code = main(
        [
            "plan",
            "query",
            "--plan-id",
            "PLAN-1",
            "--config",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 教学执行计划" in captured.out
    assert len(calls) == 1
    assert calls[0]["trust_env"] is True
    assert calls[0]["allow_manual_captcha"] is True
    assert calls[0]["filters"].plan_id == "PLAN-1"


def test_plan_query_list_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        json.dumps(
            {
                "cumt": {"username": "student", "password": "secret"},
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        cli_module,
        "query_plan_with_session_reuse",
        lambda *args, **kwargs: TeachingPlanResult(
            header=None,
            plans=(_plan_result().header,),
            total=1,
            list_only=True,
        ),
    )

    exit_code = main(
        [
            "plan",
            "query",
            "--list",
            "--grade",
            "2023",
            "--config",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "CUMT 教学执行计划列表" in captured.out
    assert "PLAN-1" in captured.out


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
        (cli_module.ConfigError("config"), ExitCode.CONFIG_ERROR),
    ],
)
def test_plan_query_maps_runtime_errors_to_exit_codes(
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
                "query": {"year": "2025", "semester": "12"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(config, *, filters, trust_env, allow_manual_captcha):
        raise raised

    monkeypatch.setattr(
        cli_module, "query_plan_with_session_reuse", raise_runtime_error
    )

    exit_code = main(
        [
            "plan",
            "query",
            "--grade",
            "2023",
            "--config",
            str(config_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err
