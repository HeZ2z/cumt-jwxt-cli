"""Schedule snapshot generation and comparison."""

from __future__ import annotations

import re
from collections.abc import Iterable

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.models import (
    ScheduleChange,
    ScheduleLesson,
    ScheduleSlot,
    ScheduleSnapshotEntry,
)

_PERIOD_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")


def create_schedule_snapshot(
    lessons: list[ScheduleLesson] | tuple[ScheduleLesson, ...],
) -> tuple[ScheduleSnapshotEntry, ...]:
    """Aggregate lessons into one snapshot entry per course and teaching class.

    Multiple kbList rows sharing the same course code and teaching class are
    merged, and their slots are sorted canonically so row order never affects
    the snapshot.
    """

    grouped: dict[tuple[str, str | None], list[ScheduleLesson]] = {}
    for lesson in lessons:
        grouped.setdefault((lesson.course_code, lesson.teaching_class), []).append(
            lesson
        )

    entries: list[ScheduleSnapshotEntry] = []
    for key in sorted(grouped, key=_identity_sort_key):
        group = grouped[key]
        first = group[0]
        slots = _canonical_slots(slot for lesson in group for slot in lesson.slots)
        entries.append(
            ScheduleSnapshotEntry(
                course_code=first.course_code,
                course_name=first.course_name,
                teaching_class=first.teaching_class,
                teacher=first.teacher,
                slots=slots,
            )
        )
    return tuple(entries)


def compare_schedule_snapshots(
    before: list[ScheduleSnapshotEntry] | tuple[ScheduleSnapshotEntry, ...],
    after: list[ScheduleSnapshotEntry] | tuple[ScheduleSnapshotEntry, ...],
) -> list[ScheduleChange]:
    """Compare two schedule snapshots and return structured changes.

    Identity is based on course code plus teaching class. Duplicate identities
    within one snapshot are ambiguous and raise SnapshotError.
    """

    before_map = _build_snapshot_map(before, "before snapshot")
    after_map = _build_snapshot_map(after, "after snapshot")

    changes: list[ScheduleChange] = []
    for key in sorted(before_map.keys() - after_map.keys(), key=_identity_sort_key):
        changes.append(
            ScheduleChange(change_type="removed", before=before_map[key], after=None)
        )
    for key in sorted(after_map.keys() - before_map.keys(), key=_identity_sort_key):
        changes.append(
            ScheduleChange(change_type="added", before=None, after=after_map[key])
        )
    for key in sorted(before_map.keys() & after_map.keys(), key=_identity_sort_key):
        before_entry = before_map[key]
        after_entry = after_map[key]
        if _schedule_fields_differ(before_entry, after_entry):
            changes.append(
                ScheduleChange(
                    change_type="updated",
                    before=before_entry,
                    after=after_entry,
                )
            )

    return changes


def _canonical_slots(slots: Iterable[ScheduleSlot]) -> tuple[ScheduleSlot, ...]:
    return tuple(sorted(set(slots), key=_slot_sort_key))


def _slot_sort_key(
    slot: ScheduleSlot,
) -> tuple[int, int, int, str, tuple[int, ...], str]:
    start, end = _period_bounds(slot.periods)
    return (
        slot.weekday,
        start,
        end,
        slot.periods,
        slot.weeks,
        slot.location or "",
    )


def _period_bounds(periods: str) -> tuple[int, int]:
    match = _PERIOD_PATTERN.match(periods)
    if match is None:
        return (0, 0)
    start = int(match[1])
    end = int(match[2]) if match[2] is not None else start
    return (start, end)


def _identity_sort_key(key: tuple[str, str | None]) -> tuple[str, str]:
    return (key[0], key[1] or "")


def _build_snapshot_map(
    entries: list[ScheduleSnapshotEntry] | tuple[ScheduleSnapshotEntry, ...],
    label: str,
) -> dict[tuple[str, str | None], ScheduleSnapshotEntry]:
    snapshot_map: dict[tuple[str, str | None], ScheduleSnapshotEntry] = {}
    for entry in entries:
        key = (entry.course_code, entry.teaching_class)
        if key in snapshot_map:
            raise SnapshotError(
                "Duplicate schedule snapshot identity in "
                f"{label}: {entry.course_code}/{entry.teaching_class or ''}"
            )
        snapshot_map[key] = entry
    return snapshot_map


def _schedule_fields_differ(
    before: ScheduleSnapshotEntry, after: ScheduleSnapshotEntry
) -> bool:
    """Compare the mutable schedule fields that trigger an updated status."""

    return (
        before.course_name != after.course_name
        or before.teacher != after.teacher
        or sorted(before.slots, key=_slot_sort_key)
        != sorted(after.slots, key=_slot_sort_key)
    )
