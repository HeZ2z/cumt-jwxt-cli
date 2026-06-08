"""Pure helpers for exam query state and result assembly."""

from __future__ import annotations

from collections.abc import Iterable

from cumt_jwxt_cli.exams.snapshot import compare_exam_snapshots, create_exam_snapshot
from cumt_jwxt_cli.grades.query_state import (
    now_iso,
    optional_iso_timestamp,
    required_iso_timestamp,
    state_with_session,
)
from cumt_jwxt_cli.models import (
    ExamInfo,
    ExamQueryResult,
    ExamScopeState,
    GradeQueryScope,
    RuntimeState,
)

# Re-export shared helpers from grades.query_state
__all__ = [
    "build_exam_query_result",
    "exam_query_scope_from_config",
    "get_exam_query_state",
    "now_iso",
    "required_iso_timestamp",
    "optional_iso_timestamp",
    "state_with_session",
]


def build_exam_query_result(
    exams: Iterable[ExamInfo],
    previous_state: RuntimeState,
    scope: GradeQueryScope,
    queried_at: str,
    notified_at: str | None = None,
) -> ExamQueryResult:
    """Build snapshot, changes, and next runtime state from parsed exams."""

    exam_records = tuple(exams)
    current_snapshot = create_exam_snapshot(list(exam_records))
    previous_scope_state = previous_state.exam_queries.get(
        scope,
        ExamScopeState(
            snapshot=(),
            last_successful_query_at=None,
            last_notified_at=None,
        ),
    )
    changes = tuple(
        compare_exam_snapshots(previous_scope_state.snapshot, current_snapshot)
    )
    normalized_queried_at = required_iso_timestamp(
        queried_at, "last_successful_query_at"
    )
    normalized_notified_at = optional_iso_timestamp(notified_at, "last_notified_at")

    exam_queries = dict(previous_state.exam_queries)
    exam_queries[scope] = ExamScopeState(
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
        exam_queries=exam_queries,
    )
    return ExamQueryResult(
        exams=exam_records,
        snapshot=current_snapshot,
        changes=changes,
        state=next_state,
    )


def exam_query_scope_from_config(year: str, semester: str) -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def get_exam_query_state(
    state: RuntimeState,
    scope: GradeQueryScope,
) -> ExamScopeState | None:
    return state.exam_queries.get(scope)
