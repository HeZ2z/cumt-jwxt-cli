"""Pure exam report generation."""

from __future__ import annotations

from collections.abc import Sequence

from jinja2 import Environment, PackageLoader, select_autoescape

from cumt_jwxt_cli.models import ExamChange, ExamInfo, ExamSnapshotEntry

_TEMPLATE_NAME = "email_report.html"
_JINJA_ENV = Environment(
    loader=PackageLoader("cumt_jwxt_cli.exams", "templates"),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_exam_text_summary(
    *,
    exams: Sequence[ExamInfo],
    changes: Sequence[ExamChange] = (),
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build a plain-text exam schedule summary."""

    term_label = format_term_label(year, semester)
    lines = [
        f"CUMT exams {term_label}",
        f"Queried at: {queried_at}",
        f"Exams: {len(exams)}",
        "",
    ]

    if changes:
        lines.append("Changed exams:")
        lines.extend(f"- {_format_exam_change(change)}" for change in changes)
        lines.append("")

    for i, exam in enumerate(exams, 1):
        lines.append(f"{i}. {exam.course_name} ({exam.course_code})")
        if exam.exam_name:
            lines.append(f"   考试名称: {exam.exam_name}")
        if exam.exam_time:
            lines.append(f"   考试时间: {exam.exam_time}")
        if exam.location:
            location = exam.location
            if exam.campus:
                location += f" ({exam.campus})"
            lines.append(f"   考试地点: {location}")
        if exam.exam_method:
            lines.append(f"   考核方式: {exam.exam_method}")
        if exam.teacher_info:
            lines.append(f"   教师: {exam.teacher_info}")
        if exam.class_schedule:
            lines.append(f"   上课时间: {exam.class_schedule}")
        if exam.credit:
            lines.append(f"   学分: {exam.credit}")
        lines.append("")

    if not exams:
        lines.append("No exams found for this term.")

    return "\n".join(lines)


_SEMESTER_LABELS: dict[str, str] = {
    "3": "第一学期",
    "12": "第二学期",
}


def format_term_label(year: str, semester: str) -> str:
    try:
        next_year = str(int(year) + 1)
    except ValueError:
        next_year = year
    semester_name = _SEMESTER_LABELS.get(semester, f"学期{semester}")
    return f"{year}-{next_year} {semester_name}"


def build_html_report(
    *,
    exams: Sequence[ExamInfo],
    changes: Sequence[ExamChange] = (),
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build an HTML exam report without writing files."""

    template = _JINJA_ENV.get_template(_TEMPLATE_NAME)
    term_label = format_term_label(year, semester)
    return template.render(
        page_title=f"CUMT 考试报告 {term_label}",
        term_label=term_label,
        queried_at=queried_at,
        stat_exams=str(len(exams)),
        stat_changes=str(len(changes)),
        changes=_build_view_changes(changes, exams),
        exam_list=_build_view_exams(exams),
    )


def _build_view_changes(
    changes: Sequence[ExamChange],
    exams: Sequence[ExamInfo],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for change in changes:
        view: dict[str, object] = {
            "change_type": change.change_type,
        }
        if change.change_type == "added" and change.after is not None:
            view["status"] = "新增"
            view["course_name"] = change.after.course_name
            view["course_code"] = change.after.course_code
            view["exam_time"] = change.after.exam_time or ""
            view["location"] = change.after.location or ""
            view["campus"] = change.after.campus or ""
            view["exam_name"] = change.after.exam_name or ""
            view["exam_method"] = change.after.exam_method or ""
        elif change.change_type == "removed" and change.before is not None:
            view["status"] = "移除"
            view["course_name"] = change.before.course_name
            view["course_code"] = change.before.course_code
            view["exam_time"] = change.before.exam_time or ""
            view["location"] = change.before.location or ""
            view["campus"] = change.before.campus or ""
            view["exam_name"] = change.before.exam_name or ""
            view["exam_method"] = change.before.exam_method or ""
        elif (
            change.change_type == "updated"
            and change.before is not None
            and change.after is not None
        ):
            view["status"] = "更新"
            view["course_name"] = change.after.course_name
            view["course_code"] = change.after.course_code
            changed_fields: list[str] = []
            for field in (
                "course_name",
                "exam_time",
                "location",
                "campus",
                "exam_name",
                "exam_method",
            ):
                before_val = getattr(change.before, field, None)
                after_val = getattr(change.after, field, None)
                if before_val != after_val:
                    changed_fields.append(field)
            view["changed_fields"] = changed_fields
            view["before"] = _snapshot_to_dict(change.before)
            view["after"] = _snapshot_to_dict(change.after)
        else:
            continue
        result.append(view)
    return result


def _snapshot_to_dict(entry: ExamSnapshotEntry) -> dict[str, str | None]:
    return {
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "exam_time": entry.exam_time,
        "location": entry.location,
        "campus": entry.campus,
        "exam_name": entry.exam_name,
        "exam_method": entry.exam_method,
    }


def _build_view_exams(exams: Sequence[ExamInfo]) -> list[dict[str, str]]:
    return [
        {
            "course_name": exam.course_name,
            "course_code": exam.course_code,
            "exam_time": exam.exam_time or "",
            "location": (
                f"{exam.location} ({exam.campus})"
                if exam.location and exam.campus
                else exam.location or ""
            ),
            "exam_name": exam.exam_name or "",
            "exam_method": exam.exam_method or "",
        }
        for exam in exams
    ]


def _format_exam_change(change: ExamChange) -> str:
    if change.change_type == "added" and change.after is not None:
        return f"[added] {_format_exam_entry(change.after)}"
    if change.change_type == "removed" and change.before is not None:
        return f"[removed] {_format_exam_entry(change.before)}"
    if (
        change.change_type == "updated"
        and change.before is not None
        and change.after is not None
    ):
        changed = _changed_field_names(change.before, change.after)
        return (
            f"[updated] {change.after.course_code} {change.after.course_name}: "
            f"{', '.join(changed)} changed"
        )
    return f"[{change.change_type}] incomplete change record"


def _format_exam_entry(entry: ExamSnapshotEntry) -> str:
    return f"{entry.course_code} {entry.course_name}"


def _changed_field_names(
    before: ExamSnapshotEntry, after: ExamSnapshotEntry
) -> list[str]:
    field_labels = {
        "course_name": "course name",
        "exam_time": "exam time",
        "location": "location",
        "campus": "campus",
        "exam_name": "exam name",
        "exam_method": "exam method",
    }
    changed: list[str] = []
    for field, label in field_labels.items():
        if getattr(before, field) != getattr(after, field):
            changed.append(label)
    return changed
