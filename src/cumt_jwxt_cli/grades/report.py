"""Pure grade report generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from jinja2 import Environment, PackageLoader, select_autoescape

from cumt_jwxt_cli.models import (
    CourseGrade,
    GradeChange,
    GradeDetail,
    GradeSnapshotEntry,
)

_TEMPLATE_NAME = "email_report.html"
_JINJA_ENV = Environment(
    loader=PackageLoader("cumt_jwxt_cli.grades", "templates"),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)
_SCORE_CLASSES = {
    "excellent": "score-excellent",
    "good": "score-good",
    "pass": "score-pass",
    "fail": "score-fail",
    "neutral": "score-neutral",
}


@dataclass(frozen=True)
class _CreditSummary:
    total_display: str | None
    omitted_courses: tuple[str, ...]


@dataclass(frozen=True)
class _ViewField:
    label: str
    value: str
    width: str
    border_class: str


@dataclass(frozen=True)
class _ViewChange:
    status: str
    course_name: str
    score_display: str
    fields: tuple[_ViewField, ...]
    detail_summary: str
    course: _ViewCourse | None


@dataclass(frozen=True)
class _DetailRow:
    name: str
    score: str
    percentage: str


@dataclass(frozen=True)
class _ViewCourse:
    course_name: str
    meta_line: str
    score: str
    total_score_display: str
    score_class: str
    info_rows: tuple[tuple[_ViewField, ...], ...]
    detail_rows: tuple[_DetailRow, ...]


def build_text_summary(
    *,
    grades: Sequence[CourseGrade],
    changes: Sequence[GradeChange],
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build a plain-text grade summary without writing files."""

    term_label = format_term_label(year, semester)
    lines = [
        f"CUMT 成绩报告 {term_label}",
        f"Queried at: {queried_at}",
        f"Changes: {len(changes)}",
        "",
    ]

    if changes:
        lines.append("Changed courses:")
        lines.extend(f"- {_format_change(change)}" for change in changes)
    else:
        lines.append("No grade changes detected.")

    lines.extend(["", "Current grades:"])
    lines.extend(f"- {_format_grade(grade)}" for grade in grades)
    return "\n".join(lines)


def build_html_report(
    *,
    grades: Sequence[CourseGrade],
    changes: Sequence[GradeChange],
    details: Sequence[GradeDetail] = (),
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build an HTML grade report without writing files."""

    detail_map = {detail.course_code: detail for detail in details}
    grade_map = {grade.course_code: grade for grade in grades}
    credit_summary = _summarize_credits(grades)
    template = _JINJA_ENV.get_template(_TEMPLATE_NAME)
    term_label = format_term_label(year, semester)
    return template.render(
        page_title=f"CUMT 成绩报告 {term_label}",
        term_label=term_label,
        queried_at=queried_at,
        stats=_build_stats(len(grades), len(changes), credit_summary),
        changes=_build_changes(changes, detail_map, grade_map),
        courses=_build_courses(grades, detail_map),
        omitted_courses="、".join(credit_summary.omitted_courses),
    )


def _build_stats(
    course_count: int,
    change_count: int,
    credit_summary: _CreditSummary,
) -> tuple[_ViewField, ...]:
    items = [
        ("当前课程数", str(course_count)),
        ("变更数量", str(change_count)),
    ]
    if credit_summary.total_display is not None:
        items.append(("总学分", credit_summary.total_display))

    return tuple(
        _ViewField(
            label=label,
            value=value,
            width=f"{100 // len(items)}%",
            border_class="" if index == len(items) - 1 else "has-stat-border",
        )
        for index, (label, value) in enumerate(items)
    )


def _build_changes(
    changes: Sequence[GradeChange],
    details: dict[str, GradeDetail],
    grades: dict[str, CourseGrade],
) -> tuple[_ViewChange, ...]:
    return tuple(
        _build_change(
            change,
            detail=details.get(change.after.course_code) if change.after else None,
            grade=grades.get(change.after.course_code) if change.after else None,
        )
        for change in changes
    )


def _build_change(
    change: GradeChange,
    *,
    detail: GradeDetail | None,
    grade: CourseGrade | None,
) -> _ViewChange:
    if change.change_type == "added" and change.after is not None:
        status = "新增"
        score_display = change.after.score
        course_name = change.after.course_name
        course_code = change.after.course_code
        fields = _change_course_fields(grade)
        course = _build_course(grade, detail) if grade is not None else None
    elif change.change_type == "removed" and change.before is not None:
        status = "移除"
        score_display = f"原成绩 {change.before.score}"
        course_name = change.before.course_name
        course_code = change.before.course_code
        fields = ()
        course = None
    elif (
        change.change_type == "updated"
        and change.before is not None
        and change.after is not None
    ):
        status = "更新"
        score_display = f"{change.before.score} -> {change.after.score}"
        course_name = change.after.course_name
        course_code = change.after.course_code
        fields = _change_course_fields(grade)
        course = (
            _build_course(
                grade,
                detail,
                total_score_display=f"{change.before.score} -> {change.after.score}",
            )
            if grade is not None
            else None
        )
    else:
        status = change.change_type
        score_display = "变更记录不完整"
        course_name = "未知课程"
        course_code = "--"
        fields = ()
        course = None

    fields = (("课程代码", course_code), *fields)
    detail_summary = _format_detail_summary(detail) if detail is not None else ""
    return _ViewChange(
        status=status,
        course_name=course_name,
        score_display=score_display,
        fields=_build_fields(fields),
        detail_summary=detail_summary,
        course=course,
    )


def _change_course_fields(grade: CourseGrade | None) -> tuple[tuple[str, str], ...]:
    if grade is None:
        return ()
    fields = (
        ("课程性质", grade.course_type),
        ("考核方式", grade.exam_type),
        ("学分", grade.credit),
        ("绩点", grade.grade_point),
        ("学分绩点", grade.credit_grade_point),
        ("任课教师", grade.teacher_name),
    )
    return tuple((label, value) for label, value in fields if value is not None)


def _build_courses(
    grades: Sequence[CourseGrade],
    details: dict[str, GradeDetail],
) -> tuple[_ViewCourse, ...]:
    return tuple(
        _build_course(grade, details.get(grade.course_code)) for grade in grades
    )


def _build_course(
    grade: CourseGrade,
    detail: GradeDetail | None,
    *,
    total_score_display: str | None = None,
) -> _ViewCourse:
    meta_parts = [grade.course_code]
    if grade.credit:
        meta_parts.append(f"{grade.credit} 学分")
    if grade.course_type:
        meta_parts.append(grade.course_type)

    fields = tuple(
        (label, value)
        for label, value in (
            ("绩点", grade.grade_point),
            ("学分绩点", grade.credit_grade_point),
            ("任课教师", grade.teacher_name),
        )
        if value
    )
    return _ViewCourse(
        course_name=grade.course_name,
        meta_line=" | ".join(meta_parts),
        score=grade.score,
        total_score_display=total_score_display or grade.score,
        score_class=_score_badge_style(grade.score),
        info_rows=_build_info_rows(fields),
        detail_rows=_build_detail_rows(detail),
    )


def _build_info_rows(
    fields: Sequence[tuple[str, str]],
) -> tuple[tuple[_ViewField, ...], ...]:
    rows: list[tuple[_ViewField, ...]] = []
    columns = 3
    width = f"{100 // columns}%"
    for index in range(0, len(fields), columns):
        pair = fields[index : index + columns]
        row = [
            _ViewField(
                label=label,
                value=value,
                width=width,
                border_class="has-field-border" if column < columns - 1 else "",
            )
            for column, (label, value) in enumerate(pair)
        ]
        row.extend(
            _ViewField(
                label="",
                value="",
                width=width,
                border_class="has-field-border" if column < columns - 1 else "",
            )
            for column in range(len(pair), columns)
        )
        rows.append(tuple(row))
    return tuple(rows)


def _build_fields(
    fields: Sequence[tuple[str, str]],
) -> tuple[_ViewField, ...]:
    width = f"{100 // len(fields)}%" if fields else "100%"
    return tuple(
        _ViewField(
            label=label,
            value=value,
            width=width,
            border_class="" if index == len(fields) - 1 else "has-field-border",
        )
        for index, (label, value) in enumerate(fields)
    )


def _build_detail_rows(
    detail: GradeDetail | None,
) -> tuple[_DetailRow, ...]:
    if detail is None or not detail.components:
        return ()

    detail_components = tuple(
        component
        for component in detail.components
        if not _is_total_component_name(component.name)
    )
    return tuple(
        _DetailRow(
            name=component.name,
            score=component.score,
            percentage=component.percentage,
        )
        for component in detail_components
    )


def _summarize_credits(grades: Sequence[CourseGrade]) -> _CreditSummary:
    total = Decimal("0")
    has_credit = False
    omitted: list[str] = []
    for grade in grades:
        if grade.credit is None:
            omitted.append(grade.course_name)
            continue
        try:
            value = Decimal(grade.credit)
        except InvalidOperation:
            omitted.append(grade.course_name)
            continue
        if value < 0:
            omitted.append(grade.course_name)
            continue
        total += value
        has_credit = True

    return _CreditSummary(
        total_display=_format_decimal(total) if has_credit else None,
        omitted_courses=tuple(omitted),
    )


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").rstrip("0").rstrip(".")


def format_term_label(year: str, semester: str) -> str:
    try:
        next_year = str(int(year) + 1)
    except ValueError:
        next_year = year
    semester_name = "第一学期" if semester == "3" else "第二学期"
    return f"{year}-{next_year}学年 {semester_name}"


def _format_change(change: GradeChange) -> str:
    if change.change_type == "added" and change.after is not None:
        return f"[added] {_format_snapshot_entry(change.after)}"
    if change.change_type == "removed" and change.before is not None:
        return f"[removed] {_format_snapshot_entry(change.before)}"
    if (
        change.change_type == "updated"
        and change.before is not None
        and change.after is not None
    ):
        return (
            f"[updated] {change.after.course_code} {change.after.course_name}: "
            f"{change.before.score} -> {change.after.score}"
        )
    return f"[{change.change_type}] incomplete change record"


def _format_snapshot_entry(entry: GradeSnapshotEntry) -> str:
    return f"{entry.course_code} {entry.course_name}: {entry.score}"


def _format_grade(grade: CourseGrade) -> str:
    parts = [grade.course_code, grade.course_name, grade.score]
    if grade.credit is not None:
        parts.append(f"credit={grade.credit}")
    if grade.grade_point is not None:
        parts.append(f"grade_point={grade.grade_point}")
    if grade.credit_grade_point is not None:
        parts.append(f"credit_grade_point={grade.credit_grade_point}")
    if grade.course_type is not None:
        parts.append(f"type={grade.course_type}")
    if grade.exam_type is not None:
        parts.append(f"exam={grade.exam_type}")
    if grade.teacher_name is not None:
        parts.append(f"teacher={grade.teacher_name}")
    return " | ".join(parts)


def _format_detail_summary(detail: GradeDetail) -> str:
    return "；".join(
        f"{component.name} {component.score} ({component.percentage})"
        for component in detail.components
        if not _is_total_component_name(component.name)
    )


def _is_total_component_name(name: str) -> bool:
    normalized = "".join(name.split())
    return normalized in {"总评", "总成绩", "最终成绩", "课程总评", "课程总成绩"}


def _score_badge_style(score: str) -> str:
    normalized = score.strip()
    try:
        numeric_score = float(normalized)
    except ValueError:
        numeric_score = None

    if numeric_score is not None:
        if numeric_score >= 90:
            return _SCORE_CLASSES["excellent"]
        if numeric_score >= 80:
            return _SCORE_CLASSES["good"]
        if numeric_score >= 60:
            return _SCORE_CLASSES["pass"]
        return _SCORE_CLASSES["fail"]

    excellent = {"优秀", "优"}
    good = {"良好", "良"}
    pass_like = {"中等", "中", "及格", "合格", "通过"}
    fail_like = {"不及格", "不合格", "不通过"}
    if normalized in excellent:
        return _SCORE_CLASSES["excellent"]
    if normalized in good:
        return _SCORE_CLASSES["good"]
    if normalized in pass_like:
        return _SCORE_CLASSES["pass"]
    if normalized in fail_like:
        return _SCORE_CLASSES["fail"]
    return _SCORE_CLASSES["neutral"]
