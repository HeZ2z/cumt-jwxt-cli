"""Exam snapshot tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.exams.snapshot import (
    compare_exam_snapshots,
    create_exam_snapshot,
)
from cumt_jwxt_cli.models import ExamChange, ExamInfo, ExamSnapshotEntry


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


def _entry(
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


class TestCreateExamSnapshot:
    def test_sorts_by_course_code(self) -> None:
        exams = [
            _exam("B002", "大学英语"),
            _exam("A001", "高等数学"),
        ]
        result = create_exam_snapshot(exams)
        assert result == (
            _entry("A001", "高等数学"),
            _entry("B002", "大学英语"),
        )

    def test_preserves_all_fields(self) -> None:
        exams = [
            _exam(
                "A001",
                "高等数学",
                exam_time="2026-06-01(08:00-10:00)",
                location="博1-A101",
                campus="南湖校区",
                exam_name="期末考试",
                exam_method="闭卷",
            ),
        ]
        result = create_exam_snapshot(exams)
        assert result == (
            _entry(
                "A001",
                "高等数学",
                exam_time="2026-06-01(08:00-10:00)",
                location="博1-A101",
                campus="南湖校区",
                exam_name="期末考试",
                exam_method="闭卷",
            ),
        )

    def test_raises_on_duplicate_course_code(self) -> None:
        exams = [
            _exam("A001", "高等数学"),
            _exam("A001", "高等数学上"),
        ]
        with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
            create_exam_snapshot(exams)


class TestCompareExamSnapshots:
    def test_all_added(self) -> None:
        changes = compare_exam_snapshots(
            before=(),
            after=(_entry("A001", "高数"), _entry("B002", "英语")),
        )
        assert changes == [
            ExamChange(
                change_type="added",
                before=None,
                after=_entry("A001", "高数"),
            ),
            ExamChange(
                change_type="added",
                before=None,
                after=_entry("B002", "英语"),
            ),
        ]

    def test_all_removed(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数"), _entry("B002", "英语")),
            after=(),
        )
        assert changes == [
            ExamChange(
                change_type="removed",
                before=_entry("A001", "高数"),
                after=None,
            ),
            ExamChange(
                change_type="removed",
                before=_entry("B002", "英语"),
                after=None,
            ),
        ]

    def test_updated_course_name(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数上"),),
            after=(_entry("A001", "高数下"),),
        )
        assert changes == [
            ExamChange(
                change_type="updated",
                before=_entry("A001", "高数上"),
                after=_entry("A001", "高数下"),
            ),
        ]

    def test_updated_exam_time(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", exam_time="2026-06-01(08:00)"),),
            after=(_entry("A001", "高数", exam_time="2026-06-02(10:00)"),),
        )
        assert changes == [
            ExamChange(
                change_type="updated",
                before=_entry("A001", "高数", exam_time="2026-06-01(08:00)"),
                after=_entry("A001", "高数", exam_time="2026-06-02(10:00)"),
            ),
        ]

    def test_updated_location(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", location="博1-A101"),),
            after=(_entry("A001", "高数", location="博2-B202"),),
        )
        assert changes[0].change_type == "updated"

    def test_updated_campus(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", campus="南湖校区"),),
            after=(_entry("A001", "高数", campus="文昌校区"),),
        )
        assert changes[0].change_type == "updated"

    def test_updated_exam_name(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", exam_name="期中考试"),),
            after=(_entry("A001", "高数", exam_name="期末考试"),),
        )
        assert changes[0].change_type == "updated"

    def test_updated_exam_method(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", exam_method="开卷"),),
            after=(_entry("A001", "高数", exam_method="闭卷"),),
        )
        assert changes[0].change_type == "updated"

    def test_no_changes(self) -> None:
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数", campus="南湖校区"),),
            after=(_entry("A001", "高数", campus="南湖校区"),),
        )
        assert changes == []

    def test_mixed_changes(self) -> None:
        changes = compare_exam_snapshots(
            before=(
                _entry("A001", "高数"),
                _entry("B002", "英语"),
                _entry("C003", "物理"),
            ),
            after=(
                _entry("A001", "高数上"),  # updated (course_name changed)
                _entry("B002", "英语"),  # unchanged
                _entry("D004", "化学"),  # added
            ),
        )
        assert changes == [
            ExamChange(
                change_type="removed",
                before=_entry("C003", "物理"),
                after=None,
            ),
            ExamChange(
                change_type="added",
                before=None,
                after=_entry("D004", "化学"),
            ),
            ExamChange(
                change_type="updated",
                before=_entry("A001", "高数"),
                after=_entry("A001", "高数上"),
            ),
        ]

    def test_sorts_by_course_code(self) -> None:
        changes = compare_exam_snapshots(
            before=(),
            after=(
                _entry("B002", "英语"),
                _entry("A001", "高数"),
            ),
        )
        assert [c.after.course_code for c in changes] == ["A001", "B002"]

    def test_raises_on_duplicate_in_before(self) -> None:
        with pytest.raises(SnapshotError, match="Duplicate"):
            compare_exam_snapshots(
                before=(_entry("A001", "高数"), _entry("A001", "高数")),
                after=(),
            )

    def test_raises_on_duplicate_in_after(self) -> None:
        with pytest.raises(SnapshotError, match="Duplicate"):
            compare_exam_snapshots(
                before=(),
                after=(_entry("A001", "高数"), _entry("A001", "高数")),
            )

    def test_none_fields_differ(self) -> None:
        """None vs string should be detected as different."""
        changes = compare_exam_snapshots(
            before=(_entry("A001", "高数"),),
            after=(_entry("A001", "高数", location="博1-A101"),),
        )
        assert len(changes) == 1
        assert changes[0].change_type == "updated"
