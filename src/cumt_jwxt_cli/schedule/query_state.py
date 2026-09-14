"""Pure helpers for schedule query state and result assembly."""

from __future__ import annotations

from collections.abc import Iterable

from cumt_jwxt_cli.grades.query_state import (
    now_iso,
    optional_iso_timestamp,
    required_iso_timestamp,
    state_with_session,
)
from cumt_jwxt_cli.models import (
    GradeQueryScope,
    PeriodTime,
    RuntimeState,
    ScheduleLesson,
    ScheduleQueryResult,
    ScheduleScopeState,
    ScheduleUnscheduledCourse,
)
from cumt_jwxt_cli.schedule.snapshot import (
    compare_schedule_snapshots,
    create_schedule_snapshot,
)

# Re-export shared helpers from grades.query_state
__all__ = [
    "build_schedule_query_result",
    "get_schedule_query_state",
    "now_iso",
    "optional_iso_timestamp",
    "required_iso_timestamp",
    "schedule_query_scope_from_config",
    "state_with_session",
]


def build_schedule_query_result(
    lessons: Iterable[ScheduleLesson],
    unscheduled: Iterable[ScheduleUnscheduledCourse],
    previous_state: RuntimeState,
    scope: GradeQueryScope,
    queried_at: str,
    notified_at: str | None = None,
    period_times: Iterable[PeriodTime] = (),
) -> ScheduleQueryResult:
    """Build snapshot, changes, and next runtime state from parsed lessons."""

    lesson_records = tuple(lessons)
    unscheduled_records = tuple(unscheduled)
    current_snapshot = create_schedule_snapshot(lesson_records)
    previous_scope_state = previous_state.schedule_queries.get(
        scope,
        ScheduleScopeState(
            snapshot=(),
            last_successful_query_at=None,
            last_notified_at=None,
        ),
    )
    changes = tuple(
        compare_schedule_snapshots(previous_scope_state.snapshot, current_snapshot)
    )
    normalized_queried_at = required_iso_timestamp(
        queried_at, "last_successful_query_at"
    )
    normalized_notified_at = optional_iso_timestamp(notified_at, "last_notified_at")

    schedule_queries = dict(previous_state.schedule_queries)
    schedule_queries[scope] = ScheduleScopeState(
        snapshot=current_snapshot,
        last_successful_query_at=normalized_queried_at,
        last_notified_at=(
            previous_scope_state.last_notified_at
            if normalized_notified_at is None
            else normalized_notified_at
        ),
    )
    next_state = RuntimeState(
        schema_version=previous_state.schema_version,
        session_cookies=dict(previous_state.session_cookies),
        session_updated_at=previous_state.session_updated_at,
        grade_queries=dict(previous_state.grade_queries),
        exam_queries=dict(previous_state.exam_queries),
        schedule_queries=schedule_queries,
    )
    return ScheduleQueryResult(
        lessons=lesson_records,
        unscheduled=unscheduled_records,
        snapshot=current_snapshot,
        changes=changes,
        state=next_state,
        period_times=tuple(period_times),
    )


def schedule_query_scope_from_config(year: str, semester: str) -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def get_schedule_query_state(
    state: RuntimeState,
    scope: GradeQueryScope,
) -> ScheduleScopeState | None:
    return state.schedule_queries.get(scope)
