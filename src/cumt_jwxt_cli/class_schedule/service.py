"""Class timetable query business orchestration."""

from __future__ import annotations

import re

from cumt_jwxt_cli.class_schedule.query_fetch import (
    ClassScheduleFilters,
    match_class_schedules,
    query_class_schedule_list,
    query_class_timetable,
)
from cumt_jwxt_cli.errors import ConfigError
from cumt_jwxt_cli.models import (
    AppConfig,
    ClassScheduleEntry,
    ClassScheduleResult,
    ScheduleLesson,
)

_PERIOD_START_PATTERN = re.compile(r"^(\d+)")


def run_class_schedule_query(
    config: AppConfig,
    client: object,
    filters: ClassScheduleFilters,
) -> ClassScheduleResult:
    """Fetch class timetable entries, select one, and return its lessons."""

    _require_scope_filter(filters)
    entries = query_class_schedule_list(config, client, filters)
    matches = match_class_schedules(entries, filters.class_query)

    if filters.list_only:
        return ClassScheduleResult(
            entry=None,
            lessons=(),
            year=config.query.year,
            semester=config.query.semester,
            entries=matches,
            total=len(matches),
            week=filters.week,
        )

    entry = _select_entry(matches, filters.class_query)
    lessons = query_class_timetable(config, client, entry)
    if filters.week is not None:
        lessons = tuple(
            lesson for lesson in lessons if _lesson_in_week(lesson, filters.week)
        )
    return ClassScheduleResult(
        entry=entry,
        lessons=tuple(sorted(lessons, key=_lesson_sort_key)),
        year=config.query.year,
        semester=config.query.semester,
        entries=matches,
        total=len(matches),
        week=filters.week,
    )


def _require_scope_filter(filters: ClassScheduleFilters) -> None:
    # The full-term list is thousands of rows; require a real narrowing filter
    # instead of paging until the safety cap and failing with a query error.
    if filters.class_query:
        return
    if any((filters.grade, filters.college, filters.major)):
        return
    raise ConfigError(
        "请提供 --class，或用 --grade/--college/--major 缩小范围（可配合 --list）。"
    )


def _select_entry(
    matches: tuple[ClassScheduleEntry, ...],
    query: str | None,
) -> ClassScheduleEntry:
    if not matches:
        target = f"“{query}”" if query else "当前筛选条件"
        raise ConfigError(f"未找到{target}对应的班级课表。")
    if len(matches) > 1:
        raise ConfigError(
            f"匹配到 {len(matches)} 个班级课表，请用 --list 查看并用 --class 指定。"
        )
    return matches[0]


def _lesson_in_week(lesson: ScheduleLesson, week: int) -> bool:
    return any(week in slot.weeks for slot in lesson.slots)


def _lesson_sort_key(lesson: ScheduleLesson) -> tuple[int, int, str, str]:
    slot = lesson.slots[0] if lesson.slots else None
    weekday = slot.weekday if slot is not None else 0
    start = _period_start(slot.periods) if slot is not None else 0
    return (weekday, start, lesson.course_code or "", lesson.course_name or "")


def _period_start(periods: str) -> int:
    match = _PERIOD_START_PATTERN.match(periods.strip())
    if match is None:
        return 0
    return int(match[1])
