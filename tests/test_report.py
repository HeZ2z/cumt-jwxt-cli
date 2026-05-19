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
    credit_grade_point: str | None = None,
    course_type: str | None = None,
    exam_type: str | None = None,
    teacher_name: str | None = None,
) -> CourseGrade:
    return CourseGrade(
        course_code=course_code,
        course_name=course_name,
        score=score,
        credit=credit,
        grade_point=grade_point,
        credit_grade_point=credit_grade_point,
        course_type=course_type,
        exam_type=exam_type,
        teacher_name=teacher_name,
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
            _grade(
                "A001",
                "高等数学",
                "95",
                credit="4.0",
                grade_point="4.5",
                credit_grade_point="18.0",
                teacher_name="张老师",
            ),
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

    assert "CUMT 成绩报告 2024-2025学年 第二学期" in summary
    assert "Changes: 2" in summary
    assert "[added] A001 高等数学: 95" in summary
    assert "[updated] B002 大学英语: 80 -> 88" in summary
    assert (
        "A001 | 高等数学 | 95 | credit=4.0 | grade_point=4.5 | "
        "credit_grade_point=18.0 | teacher=张老师"
        in summary
    )
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


def test_build_html_report_renders_email_compatible_course_cards() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "高等数学",
                "95",
                credit="4.0",
                grade_point="4.5",
                credit_grade_point="18.0",
                course_type="通识教育必修课",
                exam_type="考试",
                teacher_name="张老师",
            ),
            _grade("B002", "大学英语", "88", credit="bad-credit"),
        ),
        changes=(
            GradeChange(
                change_type="added",
                before=None,
                after=_entry("A001", "高等数学", "95"),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "CUMT 成绩报告" in html
    assert "<title>CUMT 成绩报告 2024-2025学年 第二学期</title>" in html
    assert "2024-2025学年 第二学期" in html
    assert "当前课程数" in html
    assert "变更数量" in html
    assert "总学分" in html
    assert "4" in html
    assert "总学分未计入：大学英语" in html
    assert "变更摘要" in html
    assert "A001 | 4.0 学分 | 通识教育必修课" in html
    assert "通识教育必修课" in html
    assert "学分绩点" in html
    assert "张老师" in html
    assert "任课教师" in html
    assert "A001" in html
    assert "95" in html
    assert '<table role="presentation"' in html


def test_build_html_report_escapes_external_text() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "<script>alert(1)</script>",
                "95",
                credit="4.0",
                course_type="<b>必修</b>",
                exam_type="<i>考试</i>",
                teacher_name="<img>",
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
    assert "<img>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;必修&lt;/b&gt;" in html
    assert "&lt;img&gt;" in html


def test_build_html_report_course_card_uses_compact_three_fields() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "高等数学",
                "95",
                credit="4.0",
                grade_point="4.5",
                credit_grade_point="18.0",
                course_type="通识教育必修课",
                exam_type="考试",
                teacher_name="张老师",
            ),
        ),
        changes=(),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "A001 | 4.0 学分 | 通识教育必修课" in html
    assert "绩点" in html
    assert "学分绩点" in html
    assert "18.0" in html
    assert "任课教师" in html
    assert "考试" not in html
    assert html.count("学分绩点") == 1


def test_build_html_report_updated_change_keeps_score_arrow_in_detail_total() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "高等数学",
                "95",
                credit="4.0",
                grade_point="4.5",
                credit_grade_point="18.0",
                course_type="通识教育必修课",
                teacher_name="张老师",
            ),
        ),
        changes=(
            GradeChange(
                change_type="updated",
                before=_entry("A001", "高等数学", "90"),
                after=_entry("A001", "高等数学", "95"),
            ),
        ),
        details=(
            GradeDetail(
                course_code="A001",
                course_name="高等数学",
                components=(
                    GradeDetailComponent(name="平时", percentage="30%", score="90"),
                ),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert html.count("90 -&gt; 95") == 1
    assert "总评" in html
    assert "A001 | 4.0 学分 | 通识教育必修课" in html
    assert "成绩构成：平时 90 (30%)" not in html


def test_build_html_report_course_card_keeps_columns_with_missing_fields() -> None:
    html = build_html_report(
        grades=(
            _grade(
                "A001",
                "高等数学",
                "95",
                grade_point="4.5",
            ),
        ),
        changes=(),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert "绩点" in html
    assert html.count('<td width="33%"') == 3
    assert '<td width="100%"' not in html
    assert '<td width="50%"' not in html


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

    assert "成绩构成" in html
    assert "&lt;script&gt;平时&lt;/script&gt;" in html
    assert "<script>" not in html
    assert "总评" in html


def test_build_html_report_does_not_duplicate_total_detail_row() -> None:
    html = build_html_report(
        grades=(_grade("A001", "高等数学", "95"),),
        changes=(),
        details=(
            GradeDetail(
                course_code="A001",
                course_name="高等数学",
                components=(
                    GradeDetailComponent(name="平时", percentage="30%", score="90"),
                    GradeDetailComponent(name="总评", percentage="", score="95"),
                ),
            ),
        ),
        year="2024",
        semester="12",
        queried_at="2026-05-07T12:00:00+08:00",
    )

    assert html.count("总评") == 1
