"""Grade report generation tests."""

from cumt_jwxt_cli.grades.report import build_html_report, build_text_summary
from cumt_jwxt_cli.models import (
    CourseGrade,
    GradeChange,
    GradeDetail,
    GradeDetailComponent,
    GradeSnapshotEntry,
)


def _grade(
    course_code: str,
    course_name: str,
    score: str,
    *,
    credit: str | None = None,
    grade_point: str | None = None,
) -> CourseGrade:
    return CourseGrade(
        course_code=course_code,
        course_name=course_name,
        score=score,
        credit=credit,
        grade_point=grade_point,
    )


def _entry(course_code: str, course_name: str, score: str) -> GradeSnapshotEntry:
    return GradeSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        score=score,
    )


def test_build_text_summary_highlights_changes_and_lists_current_grades() -> None:
    summary = build_text_summary(
        grades=(
            _grade("A001", "高等数学", "95", credit="4.0", grade_point="4.5"),
            _grade("B002", "大学英语", "88"),
        ),
        changes=(
            GradeChange(
                change_type="added",
                before=None,
                after=_entry("A001", "高等数学", "95"),
            ),
            GradeChange(
                change_type="updated",
                before=_entry("B002", "大学英语", "80"),
                after=_entry("B002", "大学英语", "88"),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "CUMT grades 2024-12" in summary
    assert "Changes: 2" in summary
    assert "[added] A001 高等数学: 95" in summary
    assert "[updated] B002 大学英语: 80 -> 88" in summary
    assert "A001 | 高等数学 | 95 | credit=4.0 | grade_point=4.5" in summary
    assert "B002 | 大学英语 | 88" in summary


def test_build_text_summary_reports_no_changes() -> None:
    summary = build_text_summary(
        grades=(_grade("A001", "高等数学", "95"),),
        changes=(),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "Changes: 0" in summary
    assert "No grade changes detected." in summary


def test_build_html_report_escapes_external_text() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "<script>alert(1)</script>",
                "95",
                credit="4.0",
            ),
        ),
        changes=(
            GradeChange(
                change_type="added",
                before=None,
                after=_entry("A001", "<script>alert(1)</script>", "95"),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "CUMT grades 2024-12" in html
    assert "A001" in html
    assert "95" in html


def test_build_html_report_includes_escaped_grade_details() -> None:
    html = build_html_report(
        grades=(_grade("A001", "高等数学", "95"),),
        changes=(),
        details=(
            GradeDetail(
                course_code="A001",
                course_name="<b>高等数学</b>",
                components=(
                    GradeDetailComponent(
                        name="<script>平时</script>",
                        percentage="30%",
                        score="90",
                    ),
                ),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "Grade details" in html
    assert "&lt;b&gt;高等数学&lt;/b&gt;" in html
    assert "&lt;script&gt;平时&lt;/script&gt;" in html
    assert "<script>" not in html
