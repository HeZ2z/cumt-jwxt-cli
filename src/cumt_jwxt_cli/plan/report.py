"""Pure teaching execution plan text report generation."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from cumt_jwxt_cli.models import (
    TeachingPlanCourse,
    TeachingPlanHeader,
    TeachingPlanResult,
)

_MISSING = "--"
_TERM_LABELS: dict[str, str] = {
    # The endpoint filters by 3/12/16 but returns rows labelled 1/2/3.
    "1": "第1学期",
    "3": "第1学期",
    "2": "第2学期",
    "12": "第2学期",
    "16": "第3学期",
}
_STUDY_TYPE_LABELS: dict[str, str] = {
    "zx": "主修",
    "fx": "辅修",
    "ezy": "二专业",
    "exw": "二学位",
}


def build_plan_list_text(
    *,
    plans: Sequence[TeachingPlanHeader],
    total: int,
) -> str:
    """Build a plain-text list of matched teaching plans."""

    lines = ["CUMT 教学执行计划列表", f"匹配 {total} 个教学执行计划"]
    if not plans:
        lines.append("未找到匹配的教学执行计划。")
        return "\n".join(lines)

    lines.extend(f"- {_format_plan_option(plan)}" for plan in plans)
    lines.append("提示：加 --plan-id 查看计划课程。")
    return "\n".join(lines)


def build_plan_text_summary(result: TeachingPlanResult) -> str:
    """Build a plain-text summary of one teaching plan."""

    lines = ["CUMT 教学执行计划", _format_header(result)]
    conditions = _format_conditions(result)
    if conditions:
        lines.append(f"条件：{conditions}")

    if not result.courses:
        lines.append("")
        lines.append("该计划没有匹配的课程。")
        return "\n".join(lines)

    for (year, term), courses in _group_courses(result.courses):
        lines.append("")
        lines.append(_format_term_heading(year, term))
        lines.extend(f"- {_format_course(course)}" for course in courses)
    return "\n".join(lines)


def _format_header(result: TeachingPlanResult) -> str:
    header = result.header
    if header is None:
        return f"计划：{_MISSING} | {len(result.courses)} 门"

    name = header.major_name or header.plan_id or _MISSING
    label = f"{name}（{header.grade}）" if header.grade else name
    count = header.course_count or str(len(result.courses))
    line = f"计划：{label} | {count} 门"
    if header.total_credits:
        line += f" | 总学分 {_format_credits(header.total_credits)}"
    return line


def _format_conditions(result: TeachingPlanResult) -> str:
    parts: list[str] = []
    if result.study_year or result.study_term:
        term_label = _format_term_heading(result.study_year, result.study_term)
        parts.append(f"学期 {term_label}")
    if result.course_query:
        parts.append(f"课程 {result.course_query}")
    if result.study_type:
        label = _STUDY_TYPE_LABELS.get(result.study_type, result.study_type)
        parts.append(f"类型 {label}")
    return " | ".join(parts)


def _format_plan_option(header: TeachingPlanHeader) -> str:
    grade = header.grade or _MISSING
    name = header.major_name or _MISSING
    plan_id = header.plan_id or _MISSING
    count = header.course_count or _MISSING
    credits = _format_credits(header.total_credits)
    return f"{grade} {name} | {plan_id} | {count} 门 | {credits} 学分"


def _group_courses(
    courses: Sequence[TeachingPlanCourse],
) -> list[tuple[tuple[str | None, str | None], list[TeachingPlanCourse]]]:
    groups: dict[tuple[str | None, str | None], list[TeachingPlanCourse]] = {}
    for course in courses:
        key = (course.study_year, course.study_term)
        groups.setdefault(key, []).append(course)
    return list(groups.items())


def _format_term_heading(year: str | None, term: str | None) -> str:
    if not year and not term:
        return "未指定学期"
    term_label = _TERM_LABELS.get(term or "", f"学期{term or _MISSING}")
    if not year:
        return term_label
    # Rows may already carry an academic-year range (2023-2024).
    if "-" in year:
        return f"{year} {term_label}"
    try:
        next_year = str(int(year) + 1)
    except ValueError:
        next_year = year
    return f"{year}-{next_year} {term_label}"


def _format_course(course: TeachingPlanCourse) -> str:
    name = course.course_name or course.course_code or _MISSING
    credits = f"{_format_credits(course.credits)} 学分"
    hours = f"{course.total_hours or _MISSING} 学时"
    category = course.category_name or course.class_category or _MISSING
    exam = course.exam_method or course.assessment_method or _MISSING
    return " | ".join((name, credits, hours, category, exam))


def _format_credits(value: str | None) -> str:
    if value is None:
        return _MISSING
    text = value.strip()
    if text in {"", _MISSING, "-", "None", "null"}:
        return _MISSING
    try:
        return f"{Decimal(text):.1f}"
    except (InvalidOperation, ValueError):
        return text
