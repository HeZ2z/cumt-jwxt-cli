"""Free classroom query business orchestration."""

from __future__ import annotations

import re

from cumt_jwxt_cli.classrooms.query_fetch import (
    ClassroomQueryOptions,
    ClassroomQueryResult,
    query_classrooms,
)
from cumt_jwxt_cli.models import AppConfig, FreeClassroom


def run_classroom_query(
    config: AppConfig,
    client: object,
    options: ClassroomQueryOptions,
) -> ClassroomQueryResult:
    """Fetch, sort, and display-limit free classrooms."""

    fetched = query_classrooms(config, client, options)
    ordered = sorted(fetched.classrooms, key=_sort_key)
    if options.limit > 0:
        ordered = ordered[: options.limit]
    return ClassroomQueryResult(classrooms=tuple(ordered), total=fetched.total)


def _sort_key(room: FreeClassroom) -> tuple[str, str, tuple[int, object], str]:
    return (
        room.campus or "",
        room.building or "",
        _floor_key(room.floor),
        room.room_code or "",
    )


def _floor_key(floor: str | None) -> tuple[int, object]:
    # Numeric floors sort ascending first; non-numeric floors and missing values
    # remain deterministic but come later.
    if not floor:
        return (2, "")
    stripped = floor.strip()
    if re.fullmatch(r"\d+", stripped):
        return (0, int(stripped))
    return (1, stripped)
