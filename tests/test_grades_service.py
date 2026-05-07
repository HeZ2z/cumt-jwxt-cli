"""Grade service orchestration tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import NotifyError, SnapshotError, StateError
from cumt_jwxt_cli.grades.service import build_grade_query_result, run_grade_query
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CourseGrade,
    CUMTConfig,
    GradeChange,
    GradesConfig,
    GradeSnapshotEntry,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
    RuntimeState,
)


def _grade(course_code: str, course_name: str, score: str) -> CourseGrade:
    return CourseGrade(course_code=course_code, course_name=course_name, score=score)


def _entry(course_code: str, course_name: str, score: str) -> GradeSnapshotEntry:
    return GradeSnapshotEntry(
        course_code=course_code, course_name=course_name, score=score
    )


def _state(
    snapshot: tuple[GradeSnapshotEntry, ...],
    *,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> RuntimeState:
    return RuntimeState(
        schema_version=1,
        last_grade_snapshot=snapshot,
        last_successful_query_at=last_successful_query_at,
        last_notified_at=last_notified_at,
    )


def _app_config(config_path: Path, *, notify_enabled: bool = False) -> AppConfig:
    return AppConfig(
        config_path=config_path,
        cumt=CUMTConfig(username="student", password="secret"),
        query=QueryConfig(year="2024", semester="12"),
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


class _QueryClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.posts: list[tuple[str, dict[str, str]]] = []

    def post(self, path: str, *, data: dict[str, str]) -> _QueryResponse:
        self.posts.append((path, data))
        return _QueryResponse(self.payload)


def test_build_grade_query_result_creates_snapshot_and_state_from_empty_history() -> (
    None
):
    grades = [
        _grade("B002", "大学英语", "88"),
        _grade("A001", "高等数学", "95"),
    ]

    result = build_grade_query_result(
        grades,
        previous_state=_state((), last_notified_at="2026-05-05T11:55:00+08:00"),
        queried_at="2026-05-05T12:00:00+08:00",
    )

    grades.append(_grade("C003", "大学物理", "90"))

    assert result.grades == (
        _grade("B002", "大学英语", "88"),
        _grade("A001", "高等数学", "95"),
    )
    assert result.snapshot == (
        _entry("A001", "高等数学", "95"),
        _entry("B002", "大学英语", "88"),
    )
    assert result.changes == (
        GradeChange(
            change_type="added", before=None, after=_entry("A001", "高等数学", "95")
        ),
        GradeChange(
            change_type="added", before=None, after=_entry("B002", "大学英语", "88")
        ),
    )
    assert result.state == RuntimeState(
        schema_version=1,
        last_grade_snapshot=result.snapshot,
        last_successful_query_at="2026-05-05T12:00:00+08:00",
        last_notified_at="2026-05-05T11:55:00+08:00",
    )


def test_build_grade_query_result_preserves_compare_snapshots_change_order() -> None:
    previous_state = _state(
        (
            _entry("A001", "高等数学", "95"),
            _entry("B002", "大学英语", "88"),
        )
    )

    result = build_grade_query_result(
        [
            _grade("C003", "大学物理", "91"),
            _grade("B002", "大学英语", "90"),
        ],
        previous_state=previous_state,
        queried_at="2026-05-05T12:00:00+08:00",
    )

    assert result.changes == (
        GradeChange(
            change_type="removed",
            before=_entry("A001", "高等数学", "95"),
            after=None,
        ),
        GradeChange(
            change_type="added",
            before=None,
            after=_entry("C003", "大学物理", "91"),
        ),
        GradeChange(
            change_type="updated",
            before=_entry("B002", "大学英语", "88"),
            after=_entry("B002", "大学英语", "90"),
        ),
    )
    assert result.state.last_grade_snapshot == (
        _entry("B002", "大学英语", "90"),
        _entry("C003", "大学物理", "91"),
    )


def test_build_grade_query_result_overrides_last_notified_at_when_provided() -> None:
    result = build_grade_query_result(
        [_grade("A001", "高等数学", "95")],
        previous_state=_state((), last_notified_at="2026-05-05T11:55:00+08:00"),
        queried_at="2026-05-05T12:00:00+08:00",
        notified_at="2026-05-05T12:05:00+08:00",
    )

    assert result.state.last_notified_at == "2026-05-05T12:05:00+08:00"


def test_build_grade_query_result_propagates_duplicate_snapshot_identity() -> None:
    with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
        build_grade_query_result(
            [
                _grade("A001", "高等数学", "95"),
                _grade("A001", "高等数学", "90"),
            ],
            previous_state=_state(()),
            queried_at="2026-05-05T12:00:00+08:00",
        )


def test_build_grade_query_result_rejects_missing_query_timestamp() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(
                (),
                last_successful_query_at="2026-05-05T11:00:00+08:00",
            ),
            queried_at=None,  # type: ignore[arg-type]
        )


def test_build_grade_query_result_rejects_invalid_timestamp_fields() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(()),
            queried_at="not-a-timestamp",
        )

    with pytest.raises(StateError, match="last_notified_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(()),
            queried_at="2026-05-05T12:00:00+08:00",
            notified_at="  ",
        )


def test_run_grade_query_saves_state_after_successful_query(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(
        {"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]}
    )

    result = run_grade_query(
        config,
        client,
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert result.changes == (
        GradeChange(
            change_type="added",
            before=None,
            after=_entry("A001", "高等数学", "95"),
        ),
    )
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state_payload["last_grade_snapshot"] == [
        {"course_code": "A001", "course_name": "高等数学", "score": "95"}
    ]


def test_run_grade_query_does_not_update_state_when_notify_fails(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient(
        {"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]}
    )

    def fail_email(*args: object, **kwargs: object) -> None:
        raise NotifyError("boom")

    with pytest.raises(NotifyError, match="boom"):
        run_grade_query(
            config,
            client,
            force_email=False,
            now_factory=lambda: __import__("datetime").datetime.fromisoformat(
                "2026-05-07T12:00:00+08:00"
            ),
            send_email=fail_email,
        )

    assert not (tmp_path / "state.json").exists()
