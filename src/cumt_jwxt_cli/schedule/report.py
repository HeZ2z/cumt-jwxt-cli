"""Pure personal schedule report generation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from jinja2 import Environment, PackageLoader, select_autoescape

from cumt_jwxt_cli.models import (
    PeriodTime,
    ScheduleChange,
    ScheduleLesson,
    ScheduleSlot,
    ScheduleSnapshotEntry,
)

_TEMPLATE_NAME = "email_report.html"
_JINJA_ENV = Environment(
    loader=PackageLoader("cumt_jwxt_cli.schedule", "templates"),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)

_PERIOD_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
_CLOCK_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")

PeriodLookup = Mapping[str, PeriodTime]

_WEEKDAY_LABELS: dict[int, str] = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}

_SEMESTER_LABELS: dict[str, str] = {
    "3": "第一学期",
    "12": "第二学期",
}


def format_term_label(year: str, semester: str) -> str:
    """Format the academic term label, mirroring the exam report helper."""

    try:
        next_year = str(int(year) + 1)
    except ValueError:
        next_year = year
    semester_name = _SEMESTER_LABELS.get(semester, f"学期{semester}")
    return f"{year}-{next_year} {semester_name}"


def format_weeks(weeks: tuple[int, ...]) -> str:
    """Render a normalized week set as compact ranges, for example 第1-8,10-16周."""

    if not weeks:
        return ""
    ordered = sorted(set(weeks))
    parts: list[str] = []
    start = previous = ordered[0]
    for week in ordered[1:]:
        if week == previous + 1:
            previous = week
            continue
        parts.append(_format_week_range(start, previous))
        start = previous = week
    parts.append(_format_week_range(start, previous))
    return "第" + ",".join(parts) + "周"


def build_schedule_text_summary(
    *,
    lessons: Sequence[ScheduleLesson],
    changes: Sequence[ScheduleChange] = (),
    year: str,
    semester: str,
    queried_at: str,
    period_times: Sequence[PeriodTime] = (),
) -> str:
    """Build a plain-text personal schedule summary."""

    period_lookup: dict[str, PeriodTime] = {
        period.period: period for period in period_times
    }
    term_label = format_term_label(year, semester)
    lines = [
        f"CUMT 课表 {term_label}",
        f"查询时间：{queried_at}",
        f"课程数量：{len(lessons)}",
        "",
    ]

    if changes:
        lines.append("变更：")
        for change in changes:
            lines.extend(f"- {line}" for line in _format_change(change, period_lookup))
        lines.append("")

    for index, lesson in enumerate(lessons, 1):
        lines.append(f"{index}. {lesson.course_name} ({lesson.course_code})")
        if lesson.teaching_class:
            lines.append(f"   教学班: {lesson.teaching_class}")
        if lesson.teacher:
            lines.append(f"   教师: {lesson.teacher}")
        if lesson.credits:
            lines.append(f"   学分: {lesson.credits}")
        if lesson.course_type:
            lines.append(f"   课程类型: {lesson.course_type}")
        for slot in lesson.slots:
            detail = (
                f"{_format_slot_time(slot, period_lookup)} {format_weeks(slot.weeks)}"
            )
            if slot.location:
                detail += f" {slot.location}"
            lines.append(f"   {detail}")
        lines.append("")

    if not lessons:
        lines.append("本学期暂无课程安排。")

    return "\n".join(lines)


def build_html_report(
    *,
    lessons: Sequence[ScheduleLesson],
    changes: Sequence[ScheduleChange] = (),
    year: str,
    semester: str,
    queried_at: str,
    period_times: Sequence[PeriodTime] = (),
) -> str:
    """Build an HTML personal schedule report without writing files."""

    period_lookup: dict[str, PeriodTime] = {
        period.period: period for period in period_times
    }
    template = _JINJA_ENV.get_template(_TEMPLATE_NAME)
    term_label = format_term_label(year, semester)
    return template.render(
        page_title=f"CUMT 个人课表报告 {term_label}",
        term_label=term_label,
        queried_at=queried_at,
        stat_lessons=str(len(lessons)),
        stat_changes=str(len(changes)),
        changes=_build_view_changes(changes, period_lookup),
        lesson_list=_build_view_lessons(lessons, period_lookup),
    )


def _format_change(change: ScheduleChange, period_lookup: PeriodLookup) -> list[str]:
    if change.change_type == "added" and change.after is not None:
        return [f"新增课程：{_format_entry_detail(change.after, period_lookup)}"]
    if change.change_type == "removed" and change.before is not None:
        return [f"删除课程：{_format_entry_removed(change.before, period_lookup)}"]
    if (
        change.change_type == "updated"
        and change.before is not None
        and change.after is not None
    ):
        return _format_updated(change.before, change.after, period_lookup)
    return [f"未知变更：{change.change_type}"]


def _format_entry_detail(
    entry: ScheduleSnapshotEntry, period_lookup: PeriodLookup
) -> str:
    parts: list[str] = []
    slots = entry.slots
    if slots:
        locations = {slot.location for slot in slots}
        if len(locations) <= 1:
            parts.append(
                "、".join(_format_slot_time(slot, period_lookup) for slot in slots)
            )
            weeks = {slot.weeks for slot in slots}
            if len(weeks) == 1:
                parts.append(format_weeks(slots[0].weeks))
            if slots[0].location:
                parts.append(slots[0].location)
        else:
            # Different rooms per slot: inline each location so repeated
            # weekday/period pairs stay distinguishable.
            parts.append(
                "、".join(_format_slot_label(slot, period_lookup) for slot in slots)
            )
            weeks = {slot.weeks for slot in slots}
            if len(weeks) == 1:
                parts.append(format_weeks(slots[0].weeks))
    if entry.teacher:
        parts.append(entry.teacher)
    return f"{entry.course_name}（{'，'.join(part for part in parts if part)}）"


def _format_entry_removed(
    entry: ScheduleSnapshotEntry, period_lookup: PeriodLookup
) -> str:
    slots = entry.slots
    if slots:
        locations = {slot.location for slot in slots}
        if len(locations) <= 1:
            body = "、".join(_format_slot_time(slot, period_lookup) for slot in slots)
            if slots[0].location:
                body = f"{body}，{slots[0].location}"
        else:
            body = "、".join(_format_slot_label(slot, period_lookup) for slot in slots)
    else:
        body = ""
    return f"{entry.course_name}（{body}）"


def _format_updated(
    before: ScheduleSnapshotEntry,
    after: ScheduleSnapshotEntry,
    period_lookup: PeriodLookup,
) -> list[str]:
    lines: list[str] = []
    if before.course_name != after.course_name:
        lines.append(f"课程名称变更：{before.course_name} → {after.course_name}")
    if before.teacher != after.teacher:
        lines.append(
            f"教师变更：{after.course_name} "
            f"{before.teacher or '（空）'} → {after.teacher or '（空）'}"
        )

    before_slots = sorted(before.slots, key=_slot_sort_key)
    after_slots = sorted(after.slots, key=_slot_sort_key)
    if before_slots != after_slots:
        lines.extend(
            _format_slot_changes(
                after.course_name, before_slots, after_slots, period_lookup
            )
        )

    return lines or [f"课程变更：{after.course_name}"]


def _format_slot_changes(
    course_name: str,
    before_slots: list[ScheduleSlot],
    after_slots: list[ScheduleSlot],
    period_lookup: PeriodLookup,
) -> list[str]:
    if len(before_slots) != len(after_slots):
        return [
            f"时间变更：{course_name} "
            f"{_format_slots_compact(before_slots, period_lookup)} → "
            f"{_format_slots_compact(after_slots, period_lookup)}"
        ]

    lines: list[str] = []
    for before, after in zip(before_slots, after_slots, strict=False):
        if (before.weekday, before.periods) != (after.weekday, after.periods):
            lines.append(
                f"时间变更：{course_name} "
                f"{_format_slot_time(before, period_lookup)} → "
                f"{_format_slot_time(after, period_lookup)}"
            )
        if before.location != after.location:
            lines.append(
                f"教室变更：{course_name} "
                f"{before.location or '（空）'} → {after.location or '（空）'}"
            )
        if before.weeks != after.weeks:
            lines.append(
                f"周次变更：{course_name} "
                f"{format_weeks(before.weeks)} → {format_weeks(after.weeks)}"
            )
    return lines


def _format_slot_time(slot: ScheduleSlot, period_lookup: PeriodLookup) -> str:
    weekday = _WEEKDAY_LABELS.get(slot.weekday, f"周{slot.weekday}")
    clock = _format_period_clock(slot.periods, period_lookup)
    if clock:
        return f"{weekday} {slot.periods}节 {clock}"
    return f"{weekday} {slot.periods}节"


def _format_slot_label(slot: ScheduleSlot, period_lookup: PeriodLookup) -> str:
    label = _format_slot_time(slot, period_lookup)
    return f"{label}@{slot.location}" if slot.location else label


def _format_slots_compact(
    slots: list[ScheduleSlot], period_lookup: PeriodLookup
) -> str:
    return "、".join(_format_slot_time(slot, period_lookup) for slot in slots)


def _format_period_clock(periods: str, period_lookup: PeriodLookup) -> str | None:
    match = _PERIOD_PATTERN.match(periods)
    if match is None:
        return None
    start_period = match[1]
    end_period = match[2] if match[2] is not None else start_period
    start = period_lookup.get(start_period)
    end = period_lookup.get(end_period)
    if start is None or end is None:
        return None
    start_clock = start.start.strip()
    end_clock = end.end.strip()
    if not _CLOCK_PATTERN.match(start_clock) or not _CLOCK_PATTERN.match(end_clock):
        return None
    return f"{start_clock}-{end_clock}"


def _format_week_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _slot_sort_key(slot: ScheduleSlot) -> tuple[int, str, tuple[int, ...], str]:
    return (slot.weekday, slot.periods, slot.weeks, slot.location or "")


def _build_view_changes(
    changes: Sequence[ScheduleChange], period_lookup: PeriodLookup
) -> list[dict[str, object]]:
    status_labels = {"added": "新增", "updated": "更新", "removed": "移除"}
    views: list[dict[str, object]] = []
    for change in changes:
        views.append(
            {
                "change_type": change.change_type,
                "status": status_labels.get(change.change_type, "变更"),
                "lines": _format_change(change, period_lookup),
            }
        )
    return views


def _build_view_lessons(
    lessons: Sequence[ScheduleLesson], period_lookup: PeriodLookup
) -> list[dict[str, object]]:
    return [
        {
            "course_name": lesson.course_name,
            "course_code": lesson.course_code,
            "teaching_class": lesson.teaching_class or "",
            "teacher": lesson.teacher or "",
            "credits": lesson.credits or "",
            "course_type": lesson.course_type or "",
            "slots": [
                {
                    "time": _format_slot_time(slot, period_lookup),
                    "weeks": format_weeks(slot.weeks),
                    "location": slot.location or "",
                }
                for slot in lesson.slots
            ],
        }
        for lesson in lessons
    ]
