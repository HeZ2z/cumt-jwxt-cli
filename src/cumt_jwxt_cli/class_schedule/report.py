"""Pure class timetable text report generation."""

from __future__ import annotations

from collections.abc import Sequence

from cumt_jwxt_cli.models import ClassScheduleEntry, ScheduleLesson
from cumt_jwxt_cli.schedule.report import format_term_label

_WEEKDAY_LABELS: dict[int, str] = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


def build_class_schedule_list_text(
    *,
    entries: Sequence[ClassScheduleEntry],
    total: int,
) -> str:
    """Build a plain-text list of matched class timetable entries."""

    lines = ["CUMT 班级课表列表", f"匹配 {total} 个班级课表"]
    if not entries:
        lines.append("未找到匹配的班级课表。")
        return "\n".join(lines)

    lines.extend(f"- {_format_entry(entry)}" for entry in entries)
    lines.append("提示：加 --class 代码查看课表。")
    return "\n".join(lines)


def build_class_schedule_text_summary(
    *,
    entry: ClassScheduleEntry | None,
    lessons: Sequence[ScheduleLesson],
    year: str,
    semester: str,
    week: int | None = None,
) -> str:
    """Build a plain-text class timetable summary."""

    term_label = format_term_label(year, semester)
    lines = [f"CUMT 班级课表 {term_label}"]

    if entry is not None:
        lines.append(
            f"班级：{_display(entry.class_name or entry.schedule_name)}"
            f"（{_display(entry.class_id or entry.class_code)}）"
        )

    if not lessons:
        if week is not None:
            lines.append("该周没有课程。")
        else:
            lines.append("该班级在所选学期没有课程。")
        return "\n".join(lines)

    lines.append(f"共 {len(lessons)} 个上课时段")
    lines.extend(f"- {_format_lesson(lesson)}" for lesson in lessons)
    return "\n".join(lines)


def format_week_range(weeks: tuple[int, ...]) -> str:
    """Render a week tuple as compact ranges, for example 1-4,6-8."""

    if not weeks:
        return "--"
    ordered = sorted(set(weeks))
    parts: list[str] = []
    start = previous = ordered[0]
    for week in ordered[1:]:
        if week == previous + 1:
            previous = week
            continue
        parts.append(_format_range(start, previous))
        start = previous = week
    parts.append(_format_range(start, previous))
    return ",".join(parts)


def _format_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _format_lesson(lesson: ScheduleLesson) -> str:
    slot = lesson.slots[0] if lesson.slots else None
    weekday = _WEEKDAY_LABELS.get(slot.weekday, "--") if slot is not None else "--"
    periods = f"{slot.periods}节" if slot is not None and slot.periods else "--"
    weeks = f"{format_week_range(slot.weeks)}周" if slot is not None else "--"
    location = _display(slot.location) if slot is not None else "--"
    return " | ".join(
        (
            _display(lesson.course_name),
            _display(lesson.teacher),
            f"{weekday} {periods}",
            weeks,
            location,
        )
    )


def _format_entry(entry: ClassScheduleEntry) -> str:
    name = _display(entry.class_name or entry.schedule_name)
    code = _display(entry.class_id or entry.class_code or entry.schedule_code)
    return " | ".join(
        (
            name,
            code,
            _display(entry.major_name),
            _display(entry.grade_name),
            _display(entry.campus),
        )
    )


def _display(value: str | None) -> str:
    return value if value else "--"
