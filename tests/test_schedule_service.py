"""Personal schedule service orchestration tests."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    GradeQueryScope,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OutputConfig,
    QueryConfig,
    RuntimeState,
    ScheduleChange,
    ScheduleScopeState,
    ScheduleSlot,
    ScheduleSnapshotEntry,
)
from cumt_jwxt_cli.schedule.query_fetch import (
    PERIOD_TIMES_PATH,
    SCHEDULE_LIST_PATH,
    WEEK_DATES_PATH,
)
from cumt_jwxt_cli.schedule.service import is_session_query_failure, run_schedule_query

_SCHEDULE_PAYLOAD = {
    "kbList": [
        {
            "kcmc": "高等数学",
            "kch": "A001",
            "xqj": "1",
            "jcs": "1-2",
            "zcd": "1-4周",
            "cdmc": "教一A101",
            "xm": "张三",
        }
    ],
    "sjkList": [],
}
_PERIOD_PAYLOAD = [
    {"jcmc": "1", "qssj": "08:00", "jssj": "08:50"},
    {"jcmc": "2", "qssj": "08:55", "jssj": "09:45"},
]
_WEEK_PAYLOAD = [
    {"zs": "1", "zcrq": "1(2025-09-01~2025-09-07)"},
    {"zs": "2", "zcrq": "2(2025-09-08~2025-09-14)"},
    {"zs": "3", "zcrq": "3(2025-09-15~2025-09-21)"},
    {"zs": "4", "zcrq": "4(2025-09-22~2025-09-28)"},
]


def _slot(weekday: int = 1, periods: str = "1-2") -> ScheduleSlot:
    return ScheduleSlot(
        weekday=weekday, periods=periods, weeks=(1, 2, 3, 4), location="教一A101"
    )


def _entry(course_code: str, course_name: str) -> ScheduleSnapshotEntry:
    return ScheduleSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        teaching_class=None,
        teacher="张三",
        slots=(_slot(),),
    )


def _scope(year: str = "2025", semester: str = "3") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _schedule_scope(
    snapshot: tuple[ScheduleSnapshotEntry, ...] = (),
) -> ScheduleScopeState:
    return ScheduleScopeState(
        snapshot=snapshot,
        last_successful_query_at=None,
        last_notified_at=None,
    )


def _state(
    schedule_snapshot: tuple[ScheduleSnapshotEntry, ...] = (),
    *,
    scope: GradeQueryScope | None = None,
    schedule_queries: dict[GradeQueryScope, ScheduleScopeState] | None = None,
    session_cookies: dict[str, str] | None = None,
) -> RuntimeState:
    if schedule_queries is None:
        schedule_queries = {
            (_scope() if scope is None else scope): _schedule_scope(schedule_snapshot)
        }
    return RuntimeState(
        schema_version=5,
        session_cookies={} if session_cookies is None else session_cookies,
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
        schedule_queries=schedule_queries,
    )


def _app_config(
    config_path: Path,
    *,
    notify_enabled: bool = False,
    year: str = "2025",
    semester: str = "3",
) -> AppConfig:
    return AppConfig(
        config_path=config_path,
        cumt=CUMTConfig(username="student", password="secret"),
        query=QueryConfig(year=year, semester=semester),
        http=HTTPConfig(
            timeout_seconds=30.0,
            retry_attempts=2,
            retry_backoff_seconds=1.5,
        ),
        grades=GradesConfig(include_details_on_change=True, detail_concurrency=3),
        captcha=CaptchaConfig(manual_timeout_seconds=60),
        notify=NotifyConfig(
            enabled=notify_enabled,
            smtp_host="smtp.example.test" if notify_enabled else "",
            smtp_port=465,
            username="sender-user" if notify_enabled else "",
            password="sender-password" if notify_enabled else "",
            sender="sender@example.test" if notify_enabled else "",
            recipients=("user@example.test",) if notify_enabled else (),
        ),
        logging=LoggingConfig(retention_days=14),
        output=OutputConfig(
            save_json=False, save_report=False, save_ics=False, output_dir=""
        ),
    )


class _QueryResponse:
    def __init__(
        self,
        payload: object,
        *,
        content_type: str = "application/json",
    ) -> None:
        self._payload = payload
        self.headers = {"content-type": content_type}

    status_code = 200

    def json(self) -> object:
        return self._payload


class _QueryClient:
    def __init__(
        self,
        schedule_payload: object = _SCHEDULE_PAYLOAD,
        *,
        period_payload: object = _PERIOD_PAYLOAD,
        week_payload: object = _WEEK_PAYLOAD,
        period_content_type: str = "application/json",
    ) -> None:
        self._responses = {
            SCHEDULE_LIST_PATH: _QueryResponse(schedule_payload),
            PERIOD_TIMES_PATH: _QueryResponse(
                period_payload, content_type=period_content_type
            ),
            WEEK_DATES_PATH: _QueryResponse(week_payload),
        }

    def post(self, path: str, **kwargs: object) -> _QueryResponse:
        return self._responses[path]


def _now() -> datetime:
    return datetime.fromisoformat("2026-06-01T12:00:00+08:00")


def test_run_schedule_query_saves_state_after_successful_query(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient()

    result = run_schedule_query(
        config,
        client,
        previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
        session_cookies={"JSESSIONID": "existing"},
        force_email=False,
        now_factory=_now,
    )

    assert len(result.lessons) == 1
    assert result.lessons[0].course_code == "A001"
    assert result.changes == (
        ScheduleChange(
            change_type="added",
            before=None,
            after=_entry("A001", "高等数学"),
        ),
    )
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state_payload["schema_version"] == 5
    assert state_payload["session_cookies"] == {"JSESSIONID": "existing"}


def test_run_schedule_query_keeps_semester_histories_isolated(tmp_path: Path) -> None:
    spring = _scope("2025", "3")
    autumn = _scope("2025", "12")
    previous_state = RuntimeState(
        schema_version=5,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
        schedule_queries={
            spring: _schedule_scope((_entry("A001", "高数"),)),
            autumn: _schedule_scope((_entry("B002", "英语"),)),
        },
    )
    config = _app_config(tmp_path / "config.local.json", year="2025", semester="12")
    client = _QueryClient(
        {
            "kbList": [
                {
                    "kcmc": "英语",
                    "kch": "B002",
                    "xqj": "1",
                    "jcs": "1-2",
                    "zcd": "1-4周",
                    "cdmc": "教一A101",
                    "xm": "张三",
                }
            ]
        }
    )

    result = run_schedule_query(
        config,
        client,
        previous_state=previous_state,
        force_email=False,
        now_factory=_now,
    )

    assert result.changes == ()
    assert result.state.schedule_queries[spring].snapshot == (_entry("A001", "高数"),)
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(state_payload["schedule_queries"]) == {"2025-3", "2025-12"}


def test_run_schedule_query_saves_json_with_stable_schema(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    config = AppConfig(
        config_path=config.config_path,
        cumt=config.cumt,
        query=config.query,
        http=config.http,
        grades=config.grades,
        captcha=config.captcha,
        notify=config.notify,
        logging=config.logging,
        output=OutputConfig(
            save_json=True, save_report=False, save_ics=False, output_dir=""
        ),
    )
    client = _QueryClient()

    run_schedule_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=_now,
    )

    payload = json.loads(
        (
            config.output.resolve_dir(config.config_path) / "schedules_25fa.json"
        ).read_text(encoding="utf-8")
    )
    assert set(payload) == {"lessons", "unscheduled", "changes", "summary"}
    assert set(payload["lessons"][0]) == {
        "course_code",
        "course_name",
        "teaching_class",
        "teacher",
        "credits",
        "course_type",
        "slots",
    }
    assert "session_cookies" not in payload
    assert "username" not in json.dumps(payload, ensure_ascii=False)


def test_run_schedule_query_uses_explicit_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "custom-output"
    config = _app_config(tmp_path / "config.local.json")
    config = AppConfig(
        config_path=config.config_path,
        cumt=config.cumt,
        query=config.query,
        http=config.http,
        grades=config.grades,
        captcha=config.captcha,
        notify=config.notify,
        logging=config.logging,
        output=OutputConfig(
            save_json=True,
            save_report=False,
            save_ics=False,
            output_dir=str(output_dir),
        ),
    )
    client = _QueryClient()

    run_schedule_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=_now,
    )

    assert (output_dir / "schedules_25fa.json").exists()
    assert not (tmp_path / "output" / "schedules_25fa.json").exists()


def test_run_schedule_query_saves_ics_with_events(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    config = AppConfig(
        config_path=config.config_path,
        cumt=config.cumt,
        query=config.query,
        http=config.http,
        grades=config.grades,
        captcha=config.captcha,
        notify=config.notify,
        logging=config.logging,
        output=OutputConfig(
            save_json=False, save_report=False, save_ics=True, output_dir=""
        ),
    )
    client = _QueryClient()

    run_schedule_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=_now,
    )

    ics = (tmp_path / "output" / "schedule_25fa.ics").read_text(encoding="utf-8")
    assert "BEGIN:VEVENT" in ics
    assert "SUMMARY:高等数学" in ics


def test_run_schedule_query_sends_email_when_changes_detected(
    tmp_path: Path,
) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient()
    sent_subjects: list[str] = []

    def collect_email(*args: object, subject: str, **kwargs: object) -> None:
        sent_subjects.append(subject)

    run_schedule_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=_now,
        send_email_fn=collect_email,
    )

    assert sent_subjects == ["CUMT 课表报告 2025-2026 第一学期"]


def test_run_schedule_query_does_not_update_state_when_notify_fails(
    tmp_path: Path,
) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient()

    def fail_email(*args: object, **kwargs: object) -> None:
        raise NotifyError("SMTP server not reachable")

    with pytest.raises(NotifyError, match="SMTP"):
        run_schedule_query(
            config,
            client,
            previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
            session_cookies={"JSESSIONID": "existing"},
            force_email=False,
            now_factory=_now,
            send_email_fn=fail_email,
        )

    assert not (tmp_path / "state.json").exists()


def test_run_schedule_query_degrades_when_period_times_fail(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(period_content_type="text/html")

    result = run_schedule_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=_now,
    )

    assert len(result.lessons) == 1
    assert len(result.changes) == 1
    assert (tmp_path / "state.json").exists()


def test_is_session_query_failure_re_export() -> None:
    from cumt_jwxt_cli.errors import QueryError

    assert is_session_query_failure(QueryError("failed with HTTP 901")) is True
    assert is_session_query_failure(QueryError("not valid JSON")) is False
