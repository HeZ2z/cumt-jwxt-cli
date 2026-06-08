"""Exam query state tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError, StateError
from cumt_jwxt_cli.exams.query_state import (
    build_exam_query_result,
    exam_query_scope_from_config,
    get_exam_query_state,
    state_with_session,
)
from cumt_jwxt_cli.models import (
    ExamInfo,
    ExamScopeState,
    ExamSnapshotEntry,
    GradeQueryScope,
    GradeSnapshotEntry,
    PerScopeState,
    RuntimeState,
)


def _exam(
    course_code: str,
    course_name: str,
    **overrides: str | None,
) -> ExamInfo:
    return ExamInfo(
        course_code=course_code,
        course_name=course_name,
        exam_time=overrides.get("exam_time"),
        location=overrides.get("location"),
        campus=overrides.get("campus"),
        exam_name=overrides.get("exam_name"),
        exam_method=overrides.get("exam_method"),
    )


def _exam_entry(
    course_code: str,
    course_name: str,
    **overrides: str | None,
) -> ExamSnapshotEntry:
    return ExamSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        exam_time=overrides.get("exam_time"),
        location=overrides.get("location"),
        campus=overrides.get("campus"),
        exam_name=overrides.get("exam_name"),
        exam_method=overrides.get("exam_method"),
    )


def _grade_entry(course_code: str, course_name: str, score: str) -> GradeSnapshotEntry:
    return GradeSnapshotEntry(
        course_code=course_code, course_name=course_name, score=score
    )


def _scope(year: str = "2025", semester: str = "3") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _state(
    exam_snapshot: tuple[ExamSnapshotEntry, ...] = (),
    *,
    scope: GradeQueryScope | None = None,
    exam_queries: dict[GradeQueryScope, ExamScopeState] | None = None,
    grade_queries: dict[GradeQueryScope, PerScopeState] | None = None,
    session_cookies: dict[str, str] | None = None,
) -> RuntimeState:
    if exam_queries is None:
        exam_queries = {
            (_scope() if scope is None else scope): ExamScopeState(
                snapshot=exam_snapshot,
                last_successful_query_at=None,
                last_notified_at=None,
            )
        }
    return RuntimeState(
        schema_version=4,
        session_cookies={} if session_cookies is None else session_cookies,
        session_updated_at=None,
        grade_queries={} if grade_queries is None else grade_queries,
        exam_queries=exam_queries,
    )


def test_build_exam_query_result_empty_history() -> None:
    exams = [
        _exam("A001", "高等数学"),
        _exam("B002", "大学英语"),
    ]

    result = build_exam_query_result(
        exams,
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert len(result.exams) == 2
    assert len(result.changes) == 2
    assert all(c.change_type == "added" for c in result.changes)
    assert result.state.exam_queries[_scope()].snapshot == (
        _exam_entry("A001", "高等数学"),
        _exam_entry("B002", "大学英语"),
    )


def test_build_exam_query_result_no_changes() -> None:
    result = build_exam_query_result(
        [_exam("A001", "高等数学")],
        previous_state=_state((_exam_entry("A001", "高等数学"),)),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.changes == ()


def test_build_exam_query_result_detects_updated() -> None:
    result = build_exam_query_result(
        [_exam("A001", "高等数学", location="博1-A101")],
        previous_state=_state((_exam_entry("A001", "高等数学"),)),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert len(result.changes) == 1
    assert result.changes[0].change_type == "updated"


def test_build_exam_query_result_isolates_scopes() -> None:
    spring = _scope("2025", "3")
    autumn = _scope("2025", "12")
    previous_state = _state(
        (),
        exam_queries={
            spring: ExamScopeState(
                snapshot=(_exam_entry("A001", "高数"),),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
            autumn: ExamScopeState(
                snapshot=(_exam_entry("B002", "英语"),),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
        },
    )

    result = build_exam_query_result(
        [_exam("B002", "英语")],
        previous_state=previous_state,
        scope=autumn,
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.changes == ()
    assert result.state.exam_queries[spring].snapshot == (_exam_entry("A001", "高数"),)


def test_build_exam_query_result_raises_on_duplicate_course_code() -> None:
    with pytest.raises(SnapshotError, match="Duplicate"):
        build_exam_query_result(
            [
                _exam("A001", "高数"),
                _exam("A001", "高数上"),
            ],
            previous_state=_state(()),
            scope=_scope(),
            queried_at="2026-06-01T12:00:00+08:00",
        )


def test_build_exam_query_result_rejects_invalid_timestamp() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_exam_query_result(
            [_exam("A001", "高数")],
            previous_state=_state(()),
            scope=_scope(),
            queried_at="not-a-timestamp",
        )


def test_build_exam_query_result_preserves_grade_queries() -> None:
    autumn = _scope("2025", "12")
    previous_state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={
            autumn: PerScopeState(
                snapshot=(_grade_entry("G001", "高数", "95"),),
                last_successful_query_at="2026-06-01T10:00:00+08:00",
                last_notified_at=None,
            ),
        },
        exam_queries={
            autumn: ExamScopeState(
                snapshot=(),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
        },
    )

    result = build_exam_query_result(
        [_exam("E001", "高数考试")],
        previous_state=previous_state,
        scope=autumn,
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.state.grade_queries[autumn].snapshot == (
        _grade_entry("G001", "高数", "95"),
    )


def test_build_exam_query_result_overrides_notified_at() -> None:
    result = build_exam_query_result(
        [_exam("A001", "高数")],
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
        notified_at="2026-06-01T12:05:00+08:00",
    )

    assert (
        result.state.exam_queries[_scope()].last_notified_at
        == "2026-06-01T12:05:00+08:00"
    )


def test_state_with_session_preserves_exam_and_grade_queries() -> None:
    scope = _scope()
    prev = RuntimeState(
        schema_version=4,
        session_cookies={"old": "cookie"},
        session_updated_at="2026-01-01T00:00:00+08:00",
        grade_queries={},
        exam_queries={
            scope: ExamScopeState(
                snapshot=(_exam_entry("A001", "高数"),),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
        },
    )

    result = state_with_session(
        prev,
        session_cookies={"new": "cookie"},
        session_updated_at="2026-06-01T12:00:00+08:00",
    )

    assert result.exam_queries[scope].snapshot == (_exam_entry("A001", "高数"),)
    assert result.session_cookies == {"new": "cookie"}


def test_exam_query_scope_from_config() -> None:
    assert exam_query_scope_from_config("2025", "3") == GradeQueryScope(
        year="2025", semester="3"
    )


def test_get_exam_query_state() -> None:
    scope = _scope()
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={
            scope: ExamScopeState(
                snapshot=(),
                last_successful_query_at="2026-06-01T12:00:00+08:00",
                last_notified_at=None,
            ),
        },
    )

    result = get_exam_query_state(state, scope)
    assert result is not None
    assert result.last_successful_query_at == "2026-06-01T12:00:00+08:00"


def test_get_exam_query_state_returns_none_when_missing() -> None:
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
    )

    assert get_exam_query_state(state, _scope()) is None
