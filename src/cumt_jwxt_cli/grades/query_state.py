"""Pure helpers for grade query state and result assembly."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.grades.snapshot import compare_snapshots, create_grade_snapshot
from cumt_jwxt_cli.models import (
    CourseGrade,
    GradeDetail,
    GradeQueryResult,
    GradeQueryScope,
    PerScopeState,
    RuntimeState,
)
from cumt_jwxt_cli.time_utils import normalize_optional_iso_timestamp


def build_grade_query_result(
    grades: Iterable[CourseGrade],
    previous_state: RuntimeState,
    scope: GradeQueryScope,
    queried_at: str,
    notified_at: str | None = None,
) -> GradeQueryResult:
    """Build snapshot, changes, and next runtime state from parsed grades."""

    grade_records = tuple(grades)
    current_snapshot = create_grade_snapshot(list(grade_records))
    previous_scope_state = previous_state.grade_queries.get(
        scope,
        PerScopeState(
            snapshot=(),
            last_successful_query_at=None,
            last_notified_at=None,
        ),
    )
    changes = tuple(compare_snapshots(previous_scope_state.snapshot, current_snapshot))
    normalized_queried_at = required_iso_timestamp(
        queried_at, "last_successful_query_at"
    )
    normalized_notified_at = optional_iso_timestamp(notified_at, "last_notified_at")

    grade_queries = dict(previous_state.grade_queries)
    grade_queries[scope] = PerScopeState(
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
        grade_queries=grade_queries,
    )
    return GradeQueryResult(
        grades=grade_records,
        snapshot=current_snapshot,
        changes=changes,
        details=(),
        state=next_state,
    )


def now_iso(now_factory: Callable[[], datetime] | None) -> str:
    now = now_factory() if now_factory is not None else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.isoformat()


def state_with_session(
    previous_state: RuntimeState,
    *,
    session_cookies: dict[str, str] | None,
    session_updated_at: str | None,
) -> RuntimeState:
    cookies = (
        previous_state.session_cookies if session_cookies is None else session_cookies
    )
    return RuntimeState(
        schema_version=previous_state.schema_version,
        session_cookies=dict(cookies),
        session_updated_at=(
            previous_state.session_updated_at
            if session_updated_at is None
            else session_updated_at
        ),
        grade_queries=dict(previous_state.grade_queries),
    )


def result_with_details(
    result: GradeQueryResult,
    details: tuple[GradeDetail, ...],
) -> GradeQueryResult:
    return GradeQueryResult(
        grades=result.grades,
        snapshot=result.snapshot,
        changes=result.changes,
        details=details,
        state=result.state,
    )


def grade_query_scope_from_config(year: str, semester: str) -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def get_grade_query_state(
    state: RuntimeState,
    scope: GradeQueryScope,
) -> PerScopeState | None:
    return state.grade_queries.get(scope)


def required_iso_timestamp(value: object, field_name: str) -> str:
    if value is None:
        raise StateError(f"State field {field_name} must be a string or null.")
    return optional_iso_timestamp(value, field_name)  # type: ignore[return-value]


def optional_iso_timestamp(value: object, field_name: str) -> str | None:
    return normalize_optional_iso_timestamp(
        value,
        field_label=f"State field {field_name}",
        error_factory=StateError,
    )
