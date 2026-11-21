"""Class timetable CLI tests."""

import json

import pytest

import cumt_jwxt_cli.cli as cli_module
from cumt_jwxt_cli.cli import build_parser, main
from cumt_jwxt_cli.errors import ExitCode
from cumt_jwxt_cli.models import (
    ClassScheduleEntry,
    ClassScheduleResult,
    ScheduleLesson,
    ScheduleSlot,
)


def _config_file(tmp_path):
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
    return config_path


def _entry() -> ClassScheduleEntry:
    return ClassScheduleEntry(
        schedule_code="T1",
        schedule_aux="A1",
        schedule_name="课表1",
        class_id="0810-202301",
        class_code="202301",
        class_name="计算机2023-1",
        major_name="计算机科学与技术",
        grade_name="2023",
        college_name="计算机学院",
        campus="南湖校区",
        student_count="40",
    )


def _lesson() -> ScheduleLesson:
    return ScheduleLesson(
        course_code="M1",
        course_name="高等数学",
        teaching_class=None,
        teacher="张三",
        credits=None,
        course_type=None,
        slots=(
            ScheduleSlot(
                weekday=1, periods="1-2", weeks=(1, 2, 3), location="博1-A203"
            ),
        ),
    )


def test_build_parser_parses_class_schedule_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["class-schedule", "query"])

    assert args.command == "class-schedule"
    assert args.class_schedule_command == "query"
    assert args.campus == "all"
    assert args.grade is None
    assert args.class_query is None
    assert args.list_only is False
    assert args.week is None


def test_class_schedule_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "class-schedule",
            "query",
            "--campus",
            "nanhu",
            "--grade",
            "2023",
            "--college",
            "08",
            "--major",
            "0810",
            "--class",
            "0810-202301",
            "--list",
            "--week",
            "3",
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

    assert args.campus == "nanhu"
    assert args.grade == "2023"
    assert args.college == "08"
    assert args.major == "0810"
    assert args.class_query == "0810-202301"
    assert args.list_only is True
    assert args.week == 3
    assert args.year == "2026"
    assert args.semester == "3"
    assert args.config == "config.test.json"
    assert args.no_proxy is True
    assert args.no_interactive is True
    assert args.verbose is True


def test_main_shows_help_for_class_schedule_command(capsys) -> None:
    exit_code = main(["class-schedule"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "用法: cumt-jwxt class-schedule" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["class-schedule", "query", "--week", "0"],
        ["class-schedule", "query", "--week", "31"],
        ["class-schedule", "query", "--week", "abc"],
        ["class-schedule", "query", "--campus", "unknown"],
    ],
)
def test_class_schedule_query_rejects_invalid_arguments(
    capsys, argv: list[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err != ""


def test_main_runs_class_schedule_list_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = _config_file(tmp_path)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, filters, trust_env, allow_manual_captcha):
        calls.append(
            {
                "config": config,
                "filters": filters,
                "trust_env": trust_env,
                "allow_manual_captcha": allow_manual_captcha,
            }
        )
        return ClassScheduleResult(
            entry=None,
            lessons=(),
            year="2025",
            semester="3",
            entries=(_entry(),),
            total=1,
        )

    monkeypatch.setattr(
        cli_module, "query_class_schedule_with_session_reuse", fake_query
    )

    exit_code = main(
        [
            "class-schedule",
            "query",
            "--config",
            str(config_path),
            "--list",
            "--campus",
            "nanhu",
            "--grade",
            "2023",
            "--college",
            "08",
            "--major",
            "0810",
            "--class",
            "0810",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 班级课表列表" in captured.out
    assert "提示：加 --class 代码查看课表。" in captured.out

    assert len(calls) == 1
    filters = calls[0]["filters"]
    assert filters.campus == "nanhu"
    assert filters.grade == "2023"
    assert filters.college == "08"
    assert filters.major == "0810"
    assert filters.class_query == "0810"
    assert filters.list_only is True
    assert calls[0]["trust_env"] is True
    assert calls[0]["allow_manual_captcha"] is True


def test_main_runs_class_schedule_query_workflow(capsys, tmp_path, monkeypatch) -> None:
    config_path = _config_file(tmp_path)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, filters, trust_env, allow_manual_captcha):
        calls.append({"filters": filters})
        return ClassScheduleResult(
            entry=_entry(),
            lessons=(_lesson(),),
            year="2025",
            semester="3",
            week=filters.week,
        )

    monkeypatch.setattr(
        cli_module, "query_class_schedule_with_session_reuse", fake_query
    )

    exit_code = main(
        [
            "class-schedule",
            "query",
            "--config",
            str(config_path),
            "--class",
            "0810-202301",
            "--week",
            "3",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert captured.err == ""
    assert "CUMT 班级课表 2025-2026 第一学期" in captured.out
    assert "班级：计算机2023-1（0810-202301）" in captured.out
    assert "- 高等数学 | 张三 | 周一 1-2节 | 1-3周 | 博1-A203" in captured.out
    assert calls[0]["filters"].week == 3
    assert calls[0]["filters"].list_only is False


def test_class_schedule_query_no_proxy_and_no_interactive(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = _config_file(tmp_path)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, filters, trust_env, allow_manual_captcha):
        calls.append(
            {"trust_env": trust_env, "allow_manual_captcha": allow_manual_captcha}
        )
        return ClassScheduleResult(
            entry=None, lessons=(), year="2025", semester="3", entries=(), total=0
        )

    monkeypatch.setattr(
        cli_module, "query_class_schedule_with_session_reuse", fake_query
    )

    main(
        [
            "class-schedule",
            "query",
            "--config",
            str(config_path),
            "--list",
            "--no-proxy",
            "--no-interactive",
        ]
    )

    assert calls == [{"trust_env": False, "allow_manual_captcha": False}]


def test_class_schedule_ambiguous_selection_exits_with_code_two(
    capsys, tmp_path, monkeypatch
) -> None:
    config_path = _config_file(tmp_path)

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def fake_query(config, *, filters, trust_env, allow_manual_captcha):
        raise cli_module.ConfigError(
            "匹配到 2 个班级课表，请用 --list 查看并用 --class 指定。"
        )

    monkeypatch.setattr(
        cli_module, "query_class_schedule_with_session_reuse", fake_query
    )

    exit_code = main(["class-schedule", "query", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--class" in captured.err


@pytest.mark.parametrize(
    ("raised", "expected_code"),
    [
        (cli_module.AuthError("auth"), ExitCode.AUTH_ERROR),
        (cli_module.QueryError("query"), ExitCode.QUERY_ERROR),
        (cli_module.ParseError("parse"), ExitCode.PARSE_ERROR),
    ],
)
def test_class_schedule_query_maps_runtime_errors_to_exit_codes(
    capsys,
    tmp_path,
    monkeypatch,
    raised: Exception,
    expected_code: ExitCode,
) -> None:
    config_path = _config_file(tmp_path)

    monkeypatch.setattr(cli_module, "configure_logging", lambda **kwargs: None)

    def raise_runtime_error(config, *, filters, trust_env, allow_manual_captcha):
        raise raised

    monkeypatch.setattr(
        cli_module, "query_class_schedule_with_session_reuse", raise_runtime_error
    )

    exit_code = main(
        ["class-schedule", "query", "--config", str(config_path), "--list"]
    )
    captured = capsys.readouterr()

    assert exit_code == int(expected_code)
    assert str(raised) in captured.err
