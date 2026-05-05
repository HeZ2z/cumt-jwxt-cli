"""Grade snapshot generation and comparison."""

from cumt_jwxt_cli.errors import SnapshotError
from cumt_jwxt_cli.models import CourseGrade, GradeChange, GradeSnapshotEntry


def create_grade_snapshot(grades: list[CourseGrade]) -> tuple[GradeSnapshotEntry, ...]:
    """Create a stable snapshot for grade change detection."""

    entries = [
        GradeSnapshotEntry(
            course_code=grade.course_code,
            course_name=grade.course_name,
            score=grade.score,
        )
        for grade in grades
    ]
    snapshot_map = _build_snapshot_map(entries, "grade snapshot")
    return tuple(snapshot_map[key] for key in sorted(snapshot_map))


def compare_snapshots(
    before: list[GradeSnapshotEntry] | tuple[GradeSnapshotEntry, ...],
    after: list[GradeSnapshotEntry] | tuple[GradeSnapshotEntry, ...],
) -> list[GradeChange]:
    """Compare two snapshots and return structured grade changes."""

    before_map = _build_snapshot_map(before, "before snapshot")
    after_map = _build_snapshot_map(after, "after snapshot")

    changes: list[GradeChange] = []
    for key in sorted(before_map.keys() - after_map.keys()):
        changes.append(
            GradeChange(change_type="removed", before=before_map[key], after=None)
        )
    for key in sorted(after_map.keys() - before_map.keys()):
        changes.append(
            GradeChange(change_type="added", before=None, after=after_map[key])
        )
    for key in sorted(before_map.keys() & after_map.keys()):
        before_entry = before_map[key]
        after_entry = after_map[key]
        if before_entry.score != after_entry.score:
            changes.append(
                GradeChange(
                    change_type="updated",
                    before=before_entry,
                    after=after_entry,
                )
            )
    return changes


def _build_snapshot_map(
    entries: list[GradeSnapshotEntry] | tuple[GradeSnapshotEntry, ...],
    label: str,
) -> dict[tuple[str, str], GradeSnapshotEntry]:
    snapshot_map: dict[tuple[str, str], GradeSnapshotEntry] = {}
    for entry in entries:
        identity = _snapshot_identity(entry)
        if identity in snapshot_map:
            raise SnapshotError(
                f"Duplicate snapshot identity in {label}: "
                f"{entry.course_code} / {entry.course_name}"
            )
        snapshot_map[identity] = entry
    return snapshot_map


def _snapshot_identity(entry: GradeSnapshotEntry) -> tuple[str, str]:
    return (entry.course_code, entry.course_name)
