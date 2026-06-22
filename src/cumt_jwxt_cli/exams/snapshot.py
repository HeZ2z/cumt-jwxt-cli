"""Exam snapshot generation and comparison."""

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.models import ExamChange, ExamInfo, ExamSnapshotEntry


def create_exam_snapshot(exams: list[ExamInfo]) -> tuple[ExamSnapshotEntry, ...]:
    """Create a stable snapshot for exam change detection.

    Identity is based on course_code alone — if the same course_code appears
    more than once, a SnapshotError is raised.
    """

    entries = [
        ExamSnapshotEntry(
            course_code=exam.course_code,
            course_name=exam.course_name,
            exam_time=exam.exam_time,
            location=exam.location,
            campus=exam.campus,
            exam_name=exam.exam_name,
            exam_method=exam.exam_method,
        )
        for exam in exams
    ]
    snapshot_map = _build_exam_snapshot_map(entries, "exam snapshot")
    return tuple(snapshot_map[key] for key in sorted(snapshot_map))


def compare_exam_snapshots(
    before: list[ExamSnapshotEntry] | tuple[ExamSnapshotEntry, ...],
    after: list[ExamSnapshotEntry] | tuple[ExamSnapshotEntry, ...],
) -> list[ExamChange]:
    """Compare two exam snapshots and return structured changes.

    Identity is based on course_code alone — a course name change is
    detected as an update, not a remove+add.
    """

    before_map = _build_exam_snapshot_map(before, "before snapshot")
    after_map = _build_exam_snapshot_map(after, "after snapshot")

    changes: list[ExamChange] = []
    for key in sorted(before_map.keys() - after_map.keys()):
        changes.append(
            ExamChange(change_type="removed", before=before_map[key], after=None)
        )
    for key in sorted(after_map.keys() - before_map.keys()):
        changes.append(
            ExamChange(change_type="added", before=None, after=after_map[key])
        )
    for key in sorted(before_map.keys() & after_map.keys()):
        before_entry = before_map[key]
        after_entry = after_map[key]
        if _exam_fields_differ(before_entry, after_entry):
            changes.append(
                ExamChange(
                    change_type="updated",
                    before=before_entry,
                    after=after_entry,
                )
            )

    return changes


def _build_exam_snapshot_map(
    entries: list[ExamSnapshotEntry] | tuple[ExamSnapshotEntry, ...],
    label: str,
) -> dict[str, ExamSnapshotEntry]:
    snapshot_map: dict[str, ExamSnapshotEntry] = {}
    for entry in entries:
        if entry.course_code in snapshot_map:
            raise SnapshotError(
                f"Duplicate snapshot identity in {label}: {entry.course_code}"
            )
        snapshot_map[entry.course_code] = entry
    return snapshot_map


def _exam_fields_differ(before: ExamSnapshotEntry, after: ExamSnapshotEntry) -> bool:
    """Compare all six exam fields that trigger an updated status."""
    return (
        before.course_name != after.course_name
        or before.exam_time != after.exam_time
        or before.location != after.location
        or before.campus != after.campus
        or before.exam_name != after.exam_name
        or before.exam_method != after.exam_method
    )
