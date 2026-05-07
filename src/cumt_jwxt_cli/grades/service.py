"""Pure grade query business orchestration."""

from collections.abc import Iterable
from datetime import datetime

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.grades.snapshot import compare_snapshots, create_grade_snapshot
from cumt_jwxt_cli.models import CourseGrade, GradeQueryResult, RuntimeState


def build_grade_query_result(
    grades: Iterable[CourseGrade],
    previous_state: RuntimeState,
    queried_at: str,
    notified_at: str | None = None,
) -> GradeQueryResult:
    """Build snapshot, changes, and next runtime state from parsed grades."""

    grade_records = tuple(grades)
    current_snapshot = create_grade_snapshot(list(grade_records))
    changes = tuple(
        compare_snapshots(previous_state.last_grade_snapshot, current_snapshot)
    )
    normalized_queried_at = _required_iso_timestamp(
        queried_at, "last_successful_query_at"
    )
    normalized_notified_at = _optional_iso_timestamp(
        notified_at, "last_notified_at"
    )

    next_state = RuntimeState(
        schema_version=previous_state.schema_version,
        last_grade_snapshot=current_snapshot,
        last_successful_query_at=normalized_queried_at,
        last_notified_at=(
            previous_state.last_notified_at
            if normalized_notified_at is None
            else normalized_notified_at
        ),
    )
    return GradeQueryResult(
        grades=grade_records,
        snapshot=current_snapshot,
        changes=changes,
        state=next_state,
    )


def _required_iso_timestamp(value: object, field_name: str) -> str:
    if value is None:
        raise StateError(f"State field {field_name} must be a string or null.")
    return _optional_iso_timestamp(value, field_name)  # type: ignore[return-value]


def _optional_iso_timestamp(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateError(f"State field {field_name} must be a string or null.")

    stripped = value.strip()
    if not stripped:
        raise StateError(f"State field {field_name} must not be blank when present.")

    value_to_parse = (
        stripped.removesuffix("Z") + "+00:00" if stripped.endswith("Z") else stripped
    )
    try:
        datetime.fromisoformat(value_to_parse)
    except ValueError as exc:
        raise StateError(
            f"State field {field_name} must be an ISO 8601 timestamp."
        ) from exc
    return stripped
