"""Pure course teaching-session text report generation."""

from __future__ import annotations

import re
from collections.abc import Sequence

from cumt_jwxt_cli.models import CourseSession

_WEEKDAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}
_SEMESTER_LABELS = {"3": "第一学期", "12": "第二学期"}


def build_courses_text_summary(
    *,
    sessions: Sequence[CourseSession],
    total: int,
    year: str,
    semester: str,
    course: str | None = None,
    teacher: str | None = None,
    room: str | None = None,
    weekday: int | None = None,
    periods: str | None = None,
    weeks: str | None = None,
) -> str:
    """Build a plain-text course teaching-session summary."""

    lines = [f"CUMT 上课情况 {_academic_year(year)} {_semester_label(semester)}"]
    lines.append(
        "条件："
        + _format_conditions(
            course=course,
            teacher=teacher,
            room=room,
            weekday=weekday,
            periods=periods,
            weeks=weeks,
        )
    )

    if total == 0:
        lines.append("未找到符合条件的上课记录。")
        return "\n".join(lines)

    lines.append(f"共 {total} 条，显示前 {len(sessions)} 条")
    lines.extend(f"- {_format_session(session)}" for session in sessions)
    return "\n".join(lines)


def _academic_year(year: str) -> str:
    if year.isdigit() and len(year) == 4:
        return f"{year}-{int(year) + 1}"
    return year


def _semester_label(semester: str) -> str:
    return _SEMESTER_LABELS.get(semester, semester)


def _format_conditions(
    *,
    course: str | None,
    teacher: str | None,
    room: str | None,
    weekday: int | None,
    periods: str | None,
    weeks: str | None,
) -> str:
    parts: list[str] = []
    if course:
        parts.append(f"课程={course}")
    if teacher:
        parts.append(f"教师={teacher}")
    if room:
        parts.append(f"场地={room}")
    if weekday is not None:
        parts.append(f"星期={_weekday_label(weekday)}")
    if periods:
        parts.append(f"节次={periods}")
    if weeks:
        parts.append(f"起始周={weeks}")
    return "，".join(parts) if parts else "--"


def _format_session(session: CourseSession) -> str:
    return " | ".join(
        [
            session.course_name or "--",
            session.teacher_name or "--",
            _format_schedule(session),
            _format_weeks(session.start_week),
            _format_location(session),
            _format_people(session),
            _format_credits(session.credits),
        ]
    )


def _format_schedule(session: CourseSession) -> str:
    weekday = _weekday_label(session.weekday)
    periods = session.periods or ""
    if periods and not periods.endswith("节"):
        periods = f"{periods}节"
    return f"{weekday} {periods or '--'}"


def _weekday_label(value: object) -> str:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return "--"
    return _WEEKDAY_LABELS.get(number, "--")


def _format_weeks(start_week: str | None) -> str:
    if not start_week:
        return "--"
    if start_week.endswith("周"):
        return start_week
    return f"{start_week}周"


def _format_location(session: CourseSession) -> str:
    if session.location_text:
        parts = [
            part.strip()
            for part in re.split(r"[;,；]", session.location_text)
            if part.strip()
        ]
        # The source repeats the same room once per schedule slot.
        unique = list(dict.fromkeys(parts))
        return "、".join(unique) if unique else session.location_text
    if session.room:
        return session.room
    parts = [part for part in (session.campus, session.building) if part]
    if parts:
        return " ".join(parts)
    return "--"


def _format_people(session: CourseSession) -> str:
    enrolled = session.enrolled_count
    size = session.class_size
    if enrolled and size:
        return f"{enrolled}/{size}人"
    if enrolled:
        return f"{enrolled}人"
    if size:
        return f"{size}人"
    return "--"


def _format_credits(credits: str | None) -> str:
    return f"{credits}学分" if credits else "--"
