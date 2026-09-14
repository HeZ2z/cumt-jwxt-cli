"""Schedule query state tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError, StateError
from cumt_jwxt_cli.models import (
    ExamScopeState,
    ExamSnapshotEntry,
    GradeQueryScope,
    GradeSnapshotEntry,
    PeriodTime,
    PerScopeState,
    RuntimeState,
    ScheduleLesson,
    ScheduleScopeState,
    ScheduleSlot,
    ScheduleSnapshotEntry,
    ScheduleUnscheduledCourse,
)
from cumt_jwxt_cli.schedule.query_state import (
    build_schedule_query_result,
    get_schedule_query_state,
    schedule_query_scope_from_config,
    state_with_session,
)


def _slot(weekday: int = 1, periods: str = "1-2") -> ScheduleSlot:
    return ScheduleSlot(
        weekday=weekday, periods=periods, weeks=(1, 2, 3), location="博1-A101"
    )


def _lesson(
    course_code: str,
    course_name: str,
    *,
    teaching_class: str | None = "01班",
    teacher: str | None = "张老师",
    slots: tuple[ScheduleSlot, ...] | None = None,
) -> ScheduleLesson:
    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=teaching_class,
        teacher=teacher,
        credits="3.0",
        course_type="必修",
        slots=slots if slots is not None else (_slot(),),
    )


def _entry(
    course_code: str,
    course_name: str,
    *,
    teaching_class: str | None = "01班",
    teacher: str | None = "张老师",
    slots: tuple[ScheduleSlot, ...] | None = None,
) -> ScheduleSnapshotEntry:
    return ScheduleSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        teaching_class=teaching_class,
        teacher=teacher,
        slots=slots if slots is not None else (_slot(),),
    )


def _scope(year: str = "2025", semester: str = "3") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _state(
    schedule_snapshot: tuple[ScheduleSnapshotEntry, ...] = (),
    *,
    scope: GradeQueryScope | None = None,
    schedule_queries: dict[GradeQueryScope, ScheduleScopeState] | None = None,
    grade_queries: dict[GradeQueryScope, PerScopeState] | None = None,
    exam_queries: dict[GradeQueryScope, ExamScopeState] | None = None,
) -> RuntimeState:
    if schedule_queries is None:
        schedule_queries = {
            (_scope() if scope is None else scope): ScheduleScopeState(
                snapshot=schedule_snapshot,
                last_successful_query_at=None,
                last_notified_at=None,
            )
        }
    return RuntimeState(
        schema_version=5,
        session_cookies={},
        session_updated_at=None,
        grade_queries={} if grade_queries is None else grade_queries,
        exam_queries={} if exam_queries is None else exam_queries,
        schedule_queries=schedule_queries,
    )


def test_build_schedule_query_result_empty_history() -> None:
    lessons = [_lesson("A001", "高等数学"), _lesson("B002", "大学英语")]

    result = build_schedule_query_result(
        lessons,
        (),
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert len(result.lessons) == 2
    assert len(result.changes) == 2
    assert all(change.change_type == "added" for change in result.changes)
    assert result.state.schedule_queries[_scope()].snapshot == (
        _entry("A001", "高等数学"),
        _entry("B002", "大学英语"),
    )


def test_build_schedule_query_result_no_changes() -> None:
    result = build_schedule_query_result(
        [_lesson("A001", "高等数学")],
        (),
        previous_state=_state((_entry("A001", "高等数学"),)),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.changes == ()


def test_build_schedule_query_result_detects_updated() -> None:
    result = build_schedule_query_result(
        [_lesson("A001", "高等数学", teacher="李老师")],
        (),
        previous_state=_state((_entry("A001", "高等数学"),)),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert len(result.changes) == 1
    assert result.changes[0].change_type == "updated"


def test_build_schedule_query_result_stores_period_times() -> None:
    period_times = (
        PeriodTime(period="1", start="08:00", end="08:50"),
        PeriodTime(period="2", start="08:55", end="09:45"),
    )

    result = build_schedule_query_result(
        [_lesson("A001", "高等数学")],
        (),
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
        period_times=period_times,
    )

    assert result.period_times == period_times


def test_build_schedule_query_result_defaults_period_times_to_empty() -> None:
    result = build_schedule_query_result(
        [_lesson("A001", "高等数学")],
        (),
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.period_times == ()


def test_build_schedule_query_result_keeps_unscheduled() -> None:
    unscheduled = (
        ScheduleUnscheduledCourse(
            course_name="实践课", teacher="李老师", week_range="1-4", credits="1.0"
        ),
    )

    result = build_schedule_query_result(
        [_lesson("A001", "高等数学")],
        unscheduled,
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.unscheduled == unscheduled


def test_build_schedule_query_result_isolates_scopes() -> None:
    spring = _scope("2025", "3")
    autumn = _scope("2025", "12")
    previous_state = _state(
        (),
        schedule_queries={
            spring: ScheduleScopeState(
                snapshot=(_entry("A001", "高数"),),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
            autumn: ScheduleScopeState(
                snapshot=(_entry("B002", "英语"),),
                last_successful_query_at=None,
                last_notified_at=None,
            ),
        },
    )

    result = build_schedule_query_result(
        [_lesson("B002", "英语")],
        (),
        previous_state=previous_state,
        scope=autumn,
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.changes == ()
    assert result.state.schedule_queries[spring].snapshot == (_entry("A001", "高数"),)


def test_build_schedule_query_result_raises_on_duplicate_snapshot_identity() -> None:
    previous_state = _state(
        (),
        schedule_queries={
            _scope(): ScheduleScopeState(
                snapshot=(_entry("A001", "高数"), _entry("A001", "高数")),
                last_successful_query_at=None,
                last_notified_at=None,
            )
        },
    )

    with pytest.raises(SnapshotError, match="Duplicate"):
        build_schedule_query_result(
            [_lesson("A001", "高数")],
            (),
            previous_state=previous_state,
            scope=_scope(),
            queried_at="2026-06-01T12:00:00+08:00",
        )


def test_build_schedule_query_result_rejects_invalid_timestamp() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_schedule_query_result(
            [_lesson("A001", "高数")],
            (),
            previous_state=_state(()),
            scope=_scope(),
            queried_at="not-a-timestamp",
        )


def test_build_schedule_query_result_preserves_other_queries() -> None:
    scope = _scope()
    previous_state = RuntimeState(
        schema_version=5,
        session_cookies={},
        session_updated_at=None,
        grade_queries={
            scope: PerScopeState(
                snapshot=(GradeSnapshotEntry("G001", "高数", "95"),),
                last_successful_query_at="2026-06-01T10:00:00+08:00",
                last_notified_at=None,
            )
        },
        exam_queries={
            scope: ExamScopeState(
                snapshot=(
                    ExamSnapshotEntry("E001", "高数考试", None, None, None, None, None),
                ),
                last_successful_query_at=None,
                last_notified_at=None,
            )
        },
    )

    result = build_schedule_query_result(
        [_lesson("A001", "高数")],
        (),
        previous_state=previous_state,
        scope=scope,
        queried_at="2026-06-01T12:00:00+08:00",
    )

    assert result.state.grade_queries[scope].snapshot == (
        GradeSnapshotEntry("G001", "高数", "95"),
    )
    assert result.state.exam_queries[scope].snapshot[0].course_code == "E001"


def test_build_schedule_query_result_overrides_notified_at() -> None:
    result = build_schedule_query_result(
        [_lesson("A001", "高数")],
        (),
        previous_state=_state(()),
        scope=_scope(),
        queried_at="2026-06-01T12:00:00+08:00",
        notified_at="2026-06-01T12:05:00+08:00",
    )

    assert (
        result.state.schedule_queries[_scope()].last_notified_at
        == "2026-06-01T12:05:00+08:00"
    )


def test_state_with_session_preserves_schedule_queries() -> None:
    scope = _scope()
    previous = RuntimeState(
        schema_version=5,
        session_cookies={"old": "cookie"},
        session_updated_at="2026-01-01T00:00:00+08:00",
        grade_queries={},
        exam_queries={},
        schedule_queries={
            scope: ScheduleScopeState(
                snapshot=(_entry("A001", "高数"),),
                last_successful_query_at=None,
                last_notified_at=None,
            )
        },
    )

    result = state_with_session(
        previous,
        session_cookies={"new": "cookie"},
        session_updated_at="2026-06-01T12:00:00+08:00",
    )

    assert result.schedule_queries[scope].snapshot == (_entry("A001", "高数"),)
    assert result.session_cookies == {"new": "cookie"}


def test_schedule_query_scope_from_config() -> None:
    assert schedule_query_scope_from_config("2025", "3") == GradeQueryScope(
        year="2025", semester="3"
    )


def test_get_schedule_query_state() -> None:
    scope = _scope()
    state = RuntimeState(
        schema_version=5,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
        schedule_queries={
            scope: ScheduleScopeState(
                snapshot=(),
                last_successful_query_at="2026-06-01T12:00:00+08:00",
                last_notified_at=None,
            )
        },
    )

    result = get_schedule_query_state(state, scope)
    assert result is not None
    assert result.last_successful_query_at == "2026-06-01T12:00:00+08:00"


def test_get_schedule_query_state_returns_none_when_missing() -> None:
    state = RuntimeState(
        schema_version=5,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
        schedule_queries={},
    )

    assert get_schedule_query_state(state, _scope()) is None
