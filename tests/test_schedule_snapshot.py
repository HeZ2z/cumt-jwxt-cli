"""Schedule snapshot tests."""

import pytest

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.models import (
    ScheduleChange,
    ScheduleLesson,
    ScheduleSlot,
    ScheduleSnapshotEntry,
)
from cumt_jwxt_cli.schedule.snapshot import (
    compare_schedule_snapshots,
    create_schedule_snapshot,
)


def _slot(
    weekday: int = 1,
    periods: str = "1-2",
    weeks: tuple[int, ...] = (1, 2, 3),
    location: str | None = "博1-A101",
) -> ScheduleSlot:
    return ScheduleSlot(
        weekday=weekday, periods=periods, weeks=weeks, location=location
    )


def _lesson(
    course_code: str,
    course_name: str,
    *,
    teaching_class: str | None = "01班",
    teacher: str | None = "张老师",
    credits: str | None = "3.0",
    course_type: str | None = "必修",
    slots: tuple[ScheduleSlot, ...] | None = None,
) -> ScheduleLesson:
    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=teaching_class,
        teacher=teacher,
        credits=credits,
        course_type=course_type,
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


class TestCreateScheduleSnapshot:
    def test_sorts_by_course_code(self) -> None:
        lessons = [_lesson("B002", "英语"), _lesson("A001", "高数")]

        assert create_schedule_snapshot(lessons) == (
            _entry("A001", "高数"),
            _entry("B002", "英语"),
        )

    def test_aggregates_slots_for_same_course_and_class(self) -> None:
        lessons = [
            _lesson("A001", "高数", slots=(_slot(weekday=1, periods="1-2"),)),
            _lesson("A001", "高数", slots=(_slot(weekday=3, periods="3-4"),)),
        ]

        snapshot = create_schedule_snapshot(lessons)

        assert snapshot == (
            _entry(
                "A001",
                "高数",
                slots=(
                    _slot(weekday=1, periods="1-2"),
                    _slot(weekday=3, periods="3-4"),
                ),
            ),
        )

    def test_keeps_different_teaching_classes_separate(self) -> None:
        lessons = [
            _lesson("A001", "高数", teaching_class="01班"),
            _lesson("A001", "高数", teaching_class="02班"),
        ]

        snapshot = create_schedule_snapshot(lessons)

        assert [entry.teaching_class for entry in snapshot] == ["01班", "02班"]

    def test_slot_order_does_not_affect_snapshot(self) -> None:
        forward = [
            _lesson("A001", "高数", slots=(_slot(weekday=1),)),
            _lesson("A001", "高数", slots=(_slot(weekday=2),)),
        ]
        reverse = list(reversed(forward))

        assert create_schedule_snapshot(forward) == create_schedule_snapshot(reverse)

    def test_deduplicates_identical_slots(self) -> None:
        lessons = [
            _lesson("A001", "高数", slots=(_slot(weekday=1),)),
            _lesson("A001", "高数", slots=(_slot(weekday=1),)),
        ]

        snapshot = create_schedule_snapshot(lessons)

        assert len(snapshot[0].slots) == 1

    def test_empty_input(self) -> None:
        assert create_schedule_snapshot([]) == ()


class TestCompareScheduleSnapshots:
    def test_all_added(self) -> None:
        changes = compare_schedule_snapshots(
            before=(),
            after=(_entry("A001", "高数"), _entry("B002", "英语")),
        )

        assert changes == [
            ScheduleChange(
                change_type="added", before=None, after=_entry("A001", "高数")
            ),
            ScheduleChange(
                change_type="added", before=None, after=_entry("B002", "英语")
            ),
        ]

    def test_all_removed(self) -> None:
        changes = compare_schedule_snapshots(
            before=(_entry("A001", "高数"), _entry("B002", "英语")),
            after=(),
        )

        assert changes == [
            ScheduleChange(
                change_type="removed", before=_entry("A001", "高数"), after=None
            ),
            ScheduleChange(
                change_type="removed", before=_entry("B002", "英语"), after=None
            ),
        ]

    def test_updated_course_name(self) -> None:
        changes = compare_schedule_snapshots(
            before=(_entry("A001", "高数上"),),
            after=(_entry("A001", "高数下"),),
        )

        assert changes == [
            ScheduleChange(
                change_type="updated",
                before=_entry("A001", "高数上"),
                after=_entry("A001", "高数下"),
            )
        ]

    def test_updated_teacher(self) -> None:
        changes = compare_schedule_snapshots(
            before=(_entry("A001", "高数", teacher="张老师"),),
            after=(_entry("A001", "高数", teacher="李老师"),),
        )

        assert changes[0].change_type == "updated"

    def test_updated_slots(self) -> None:
        changes = compare_schedule_snapshots(
            before=(_entry("A001", "高数", slots=(_slot(weekday=1),)),),
            after=(_entry("A001", "高数", slots=(_slot(weekday=2),)),),
        )

        assert changes[0].change_type == "updated"

    def test_slot_order_difference_is_not_a_change(self) -> None:
        before = (_entry("A001", "高数", slots=(_slot(weekday=1), _slot(weekday=2))),)
        after = (_entry("A001", "高数", slots=(_slot(weekday=2), _slot(weekday=1))),)

        assert compare_schedule_snapshots(before, after) == []

    def test_no_changes(self) -> None:
        assert (
            compare_schedule_snapshots(
                before=(_entry("A001", "高数"),),
                after=(_entry("A001", "高数"),),
            )
            == []
        )

    def test_mixed_changes(self) -> None:
        changes = compare_schedule_snapshots(
            before=(
                _entry("A001", "高数"),
                _entry("B002", "英语"),
                _entry("C003", "物理"),
            ),
            after=(
                _entry("A001", "高数上"),
                _entry("B002", "英语"),
                _entry("D004", "化学"),
            ),
        )

        assert changes == [
            ScheduleChange(
                change_type="removed", before=_entry("C003", "物理"), after=None
            ),
            ScheduleChange(
                change_type="added", before=None, after=_entry("D004", "化学")
            ),
            ScheduleChange(
                change_type="updated",
                before=_entry("A001", "高数"),
                after=_entry("A001", "高数上"),
            ),
        ]

    def test_raises_on_duplicate_identity_in_before(self) -> None:
        with pytest.raises(SnapshotError, match="Duplicate"):
            compare_schedule_snapshots(
                before=(_entry("A001", "高数"), _entry("A001", "高数")),
                after=(),
            )

    def test_raises_on_duplicate_identity_in_after(self) -> None:
        with pytest.raises(SnapshotError, match="Duplicate"):
            compare_schedule_snapshots(
                before=(),
                after=(_entry("A001", "高数"), _entry("A001", "高数")),
            )
