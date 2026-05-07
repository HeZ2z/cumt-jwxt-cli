"""Pure grade report generation."""

from collections.abc import Sequence
from html import escape

from cumt_jwxt_cli.models import CourseGrade, GradeChange, GradeSnapshotEntry


def build_text_summary(
    *,
    grades: Sequence[CourseGrade],
    changes: Sequence[GradeChange],
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build a plain-text grade summary without writing files."""

    lines = [
        f"CUMT grades {year}-{semester}",
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
    year: str,
    semester: str,
    queried_at: str,
) -> str:
    """Build an HTML grade report without writing files."""

    change_items = (
        "\n".join(f"<li>{escape(_format_change(change))}</li>" for change in changes)
        if changes
        else "<li>No grade changes detected.</li>"
    )
    grade_rows = "\n".join(_grade_row(grade) for grade in grades)

    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{escape(f'CUMT grades {year}-{semester}')}</title>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{escape(f'CUMT grades {year}-{semester}')}</h1>\n"
        f"  <p>Queried at: {escape(queried_at)}</p>\n"
        f"  <p>Changes: {len(changes)}</p>\n"
        "  <h2>Changed courses</h2>\n"
        f"  <ul>{change_items}</ul>\n"
        "  <h2>Current grades</h2>\n"
        "  <table>\n"
        "    <thead>\n"
        "      <tr>"
        "<th>Course code</th><th>Course name</th><th>Score</th>"
        "<th>Credit</th><th>Grade point</th>"
        "</tr>\n"
        "    </thead>\n"
        f"    <tbody>\n{grade_rows}\n    </tbody>\n"
        "  </table>\n"
        "</body>\n"
        "</html>\n"
    )


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
    if grade.course_type is not None:
        parts.append(f"type={grade.course_type}")
    if grade.exam_type is not None:
        parts.append(f"exam={grade.exam_type}")
    return " | ".join(parts)


def _grade_row(grade: CourseGrade) -> str:
    cells = (
        grade.course_code,
        grade.course_name,
        grade.score,
        grade.credit or "",
        grade.grade_point or "",
    )
    cell_html = "".join(f"<td>{escape(cell)}</td>" for cell in cells)
    return f"      <tr>{cell_html}</tr>"
