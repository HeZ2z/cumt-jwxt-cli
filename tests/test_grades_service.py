"""Grade service orchestration tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError, StateError
from cumt_jwxt_cli.grades.service import build_grade_query_result
from cumt_jwxt_cli.models import (
    CourseGrade,
    GradeChange,
    GradeSnapshotEntry,
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
