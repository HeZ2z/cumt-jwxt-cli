"""Exam service orchestration tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.exams.service import run_exam_query
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    ExamChange,
    ExamInfo,
    ExamScopeState,
    ExamSnapshotEntry,
    GradeQueryScope,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
    RuntimeState,
)


def _exam(course_code: str, course_name: str) -> ExamInfo:
    return ExamInfo(course_code=course_code, course_name=course_name)


def _entry(course_code: str, course_name: str) -> ExamSnapshotEntry:
    return ExamSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        exam_time=None,
        location=None,
        campus=None,
        exam_name=None,
        exam_method=None,
    )


def _scope(year: str = "2025", semester: str = "3") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _exam_scope(
    snapshot: tuple[ExamSnapshotEntry, ...] = (),
    *,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> ExamScopeState:
    return ExamScopeState(
        snapshot=snapshot,
        last_successful_query_at=last_successful_query_at,
        last_notified_at=last_notified_at,
    )


def _state(
    exam_snapshot: tuple[ExamSnapshotEntry, ...] = (),
    *,
    scope: GradeQueryScope | None = None,
    exam_queries: dict[GradeQueryScope, ExamScopeState] | None = None,
    session_cookies: dict[str, str] | None = None,
) -> RuntimeState:
    if exam_queries is None:
        exam_queries = {
            (_scope() if scope is None else scope): _exam_scope(
                snapshot=exam_snapshot,
            )
        }
    return RuntimeState(
        schema_version=4,
        session_cookies={} if session_cookies is None else session_cookies,
        session_updated_at=None,
        grade_queries={},
        exam_queries=exam_queries,
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
        captcha=CaptchaConfig(
            provider="openai_compatible",
            manual_timeout_seconds=60,
            openai_compatible=OpenAICompatibleConfig(base_url="", api_key="", model=""),
        ),
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
        output=OutputConfig(save_json=False, save_report=False, output_dir=""),
    )


class _QueryResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload

    status_code = 200
    headers = {"content-type": "application/json"}


class _QueryClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def post(self, path: str, **kwargs: object) -> _QueryResponse:
        return _QueryResponse(self.payload)


def test_run_exam_query_saves_state_after_successful_query(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学"}]})

    result = run_exam_query(
        config,
        client,
        previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
        session_cookies={"JSESSIONID": "existing"},
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-06-01T12:00:00+08:00"
        ),
    )

    assert len(result.exams) == 1
    assert result.exams[0].course_code == "A001"
    assert result.changes == (
        ExamChange(
            change_type="added",
            before=None,
            after=_entry("A001", "高等数学"),
        ),
    )
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state_payload["schema_version"] == 4
    assert state_payload["session_cookies"] == {"JSESSIONID": "existing"}


def test_run_exam_query_keeps_semester_histories_isolated(tmp_path: Path) -> None:
    spring = _scope("2025", "3")
    autumn = _scope("2025", "12")
    previous_state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={
            spring: _exam_scope(snapshot=(_entry("A001", "高数"),)),
            autumn: _exam_scope(snapshot=(_entry("B002", "英语"),)),
        },
    )
    config = _app_config(tmp_path / "config.local.json", year="2025", semester="12")
    client = _QueryClient({"items": [{"kch": "B002", "kcmc": "英语"}]})

    result = run_exam_query(
        config,
        client,
        previous_state=previous_state,
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-06-01T12:00:00+08:00"
        ),
    )

    assert result.changes == ()
    assert result.state.exam_queries[spring].snapshot == (_entry("A001", "高数"),)
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(state_payload["exam_queries"]) == {"2025-3", "2025-12"}


def test_run_exam_query_saves_json_with_stable_schema(tmp_path: Path) -> None:
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
        output=OutputConfig(save_json=True, save_report=False, output_dir=""),
    )
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学"}]})

    run_exam_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-06-01T12:00:00+08:00"
        ),
    )

    payload = json.loads(
        (config.output.resolve_dir(config.config_path) / "exams.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(payload) == {"exams", "changes", "summary"}
    assert set(payload["exams"][0]) == {
        "course_code",
        "course_name",
        "exam_time",
        "location",
        "campus",
        "exam_name",
        "exam_method",
        "class_schedule",
        "teacher_info",
        "credit",
    }
    assert "session_cookies" not in payload
    assert "username" not in json.dumps(payload, ensure_ascii=False)


def test_run_exam_query_uses_explicit_output_dir(tmp_path: Path) -> None:
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
            save_json=True, save_report=False, output_dir=str(output_dir)
        ),
    )
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学"}]})

    run_exam_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-06-01T12:00:00+08:00"
        ),
    )

    assert (output_dir / "exams.json").exists()
    assert not (tmp_path / "output" / "exams.json").exists()


def test_run_exam_query_sends_email_when_changes_detected(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学"}]})
    sent_subjects: list[str] = []

    def collect_email(*args: object, subject: str, **kwargs: object) -> None:
        sent_subjects.append(subject)

    run_exam_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-06-01T12:00:00+08:00"
        ),
        send_email=collect_email,
    )

    assert sent_subjects == ["CUMT 考试报告 2025-2026 第一学期"]


def test_run_exam_query_does_not_update_state_when_notify_fails(tmp_path: Path) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学"}]})

    def fail_email(*args: object, **kwargs: object) -> None:
        raise NotifyError("SMTP server not reachable")

    with pytest.raises(NotifyError, match="SMTP"):
        run_exam_query(
            config,
            client,
            previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
            session_cookies={"JSESSIONID": "existing"},
            force_email=False,
            now_factory=lambda: __import__("datetime").datetime.fromisoformat(
                "2026-06-01T12:00:00+08:00"
            ),
            send_email=fail_email,
        )

    assert not (tmp_path / "state.json").exists()
