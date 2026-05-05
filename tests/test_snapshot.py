"""Grade snapshot tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.grades.snapshot import compare_snapshots, create_grade_snapshot
from cumt_jwxt_cli.models import CourseGrade, GradeChange, GradeSnapshotEntry


def test_create_grade_snapshot_is_stable_across_input_order() -> None:
    grades_a = [
        CourseGrade(course_code="B002", course_name="大学英语", score="88"),
        CourseGrade(course_code="A001", course_name="高等数学", score="95"),
    ]
    grades_b = list(reversed(grades_a))

    assert create_grade_snapshot(grades_a) == create_grade_snapshot(grades_b)


def test_compare_snapshots_detects_added_course() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95")
    ]
    after = before + [
        GradeSnapshotEntry(course_code="B002", course_name="大学英语", score="88")
    ]

    assert compare_snapshots(before, after) == [
        GradeChange(
            change_type="added",
            before=None,
            after=GradeSnapshotEntry(
                course_code="B002", course_name="大学英语", score="88"
            ),
        )
    ]


def test_compare_snapshots_detects_updated_score() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="90")
    ]
    after = [GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95")]

    assert compare_snapshots(before, after) == [
        GradeChange(
            change_type="updated",
            before=GradeSnapshotEntry(
                course_code="A001", course_name="高等数学", score="90"
            ),
            after=GradeSnapshotEntry(
                course_code="A001", course_name="高等数学", score="95"
            ),
        )
    ]


def test_compare_snapshots_detects_removed_course() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95")
    ]
    after: list[GradeSnapshotEntry] = []

    assert compare_snapshots(before, after) == [
        GradeChange(
            change_type="removed",
            before=GradeSnapshotEntry(
                course_code="A001", course_name="高等数学", score="95"
            ),
            after=None,
        )
    ]


def test_compare_snapshots_uses_course_code_and_name_as_identity() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95")
    ]
    after = [GradeSnapshotEntry(course_code="A001", course_name="线性代数", score="95")]

    assert compare_snapshots(before, after) == [
        GradeChange(
            change_type="removed",
            before=GradeSnapshotEntry(
                course_code="A001", course_name="高等数学", score="95"
            ),
            after=None,
        ),
        GradeChange(
            change_type="added",
            before=None,
            after=GradeSnapshotEntry(
                course_code="A001", course_name="线性代数", score="95"
            ),
        ),
    ]


def test_compare_snapshots_ignores_order_differences() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
        GradeSnapshotEntry(course_code="B002", course_name="大学英语", score="88"),
    ]
    after = list(reversed(before))

    assert compare_snapshots(before, after) == []


def test_create_grade_snapshot_rejects_duplicate_identity() -> None:
    grades = [
        CourseGrade(course_code="A001", course_name="高等数学", score="95"),
        CourseGrade(course_code="A001", course_name="高等数学", score="90"),
    ]

    with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
        create_grade_snapshot(grades)


def test_compare_snapshots_rejects_duplicate_identity_in_before() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="90"),
    ]
    after = [
        GradeSnapshotEntry(course_code="B002", course_name="大学英语", score="88"),
    ]

    with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
        compare_snapshots(before, after)


def test_compare_snapshots_rejects_duplicate_identity_in_after() -> None:
    before = [
        GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
    ]
    after = [
        GradeSnapshotEntry(course_code="B002", course_name="大学英语", score="88"),
        GradeSnapshotEntry(course_code="B002", course_name="大学英语", score="89"),
    ]

    with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
        compare_snapshots(before, after)
