"""Exam report generation tests."""

from cumt_jwxt_cli.exams.report import (
    build_exam_text_summary,
    build_html_report,
    format_term_label,
)
from cumt_jwxt_cli.models import ExamChange, ExamInfo, ExamSnapshotEntry


def _exam(
    course_code: str,
    course_name: str,
    **overrides: str | None,
) -> ExamInfo:
    return ExamInfo(
        course_code=course_code,
        course_name=course_name,
        exam_time=overrides.get("exam_time"),
        location=overrides.get("location"),
        campus=overrides.get("campus"),
        exam_name=overrides.get("exam_name"),
        exam_method=overrides.get("exam_method"),
        class_schedule=overrides.get("class_schedule"),
        teacher_info=overrides.get("teacher_info"),
        credit=overrides.get("credit"),
    )


def _entry(
    course_code: str,
    course_name: str,
    **overrides: str | None,
) -> ExamSnapshotEntry:
    return ExamSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        exam_time=overrides.get("exam_time"),
        location=overrides.get("location"),
        campus=overrides.get("campus"),
        exam_name=overrides.get("exam_name"),
        exam_method=overrides.get("exam_method"),
    )


class TestBuildExamTextSummary:
    def test_with_exams(self) -> None:
        exams = [
            _exam(
                "CODE1",
                "Course 1",
                exam_time="2026-06-01(08:00-10:00)",
                location="博1-A101",
                campus="南湖校区",
                exam_name="期末考试",
                exam_method="闭卷",
                class_schedule="周一第1-2节",
                teacher_info="张老师",
                credit="3.0",
            ),
            _exam("CODE2", "Course 2"),
        ]
        result = build_exam_text_summary(
            exams=exams,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT exams 2025-2026 第一学期" in result
        assert "Queried at: 2026-06-03T12:00:00" in result
        assert "Exams: 2" in result
        assert "1. Course 1 (CODE1)" in result
        assert "期末考试" in result
        assert "博1-A101" in result
        assert "南湖校区" in result
        assert "闭卷" in result
        assert "张老师" in result
        assert "周一第1-2节" in result
        assert "3.0" in result
        assert "2. Course 2 (CODE2)" in result

    def test_empty(self) -> None:
        result = build_exam_text_summary(
            exams=[],
            year="2025",
            semester="12",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT exams 2025-2026 第二学期" in result
        assert "Exams: 0" in result
        assert "No exams found for this term." in result

    def test_with_changes_added(self) -> None:
        exams = [_exam("A001", "高数")]
        changes = [
            ExamChange(
                change_type="added",
                before=None,
                after=_entry("A001", "高数"),
            ),
        ]
        result = build_exam_text_summary(
            exams=exams,
            changes=changes,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "[added] A001 高数" in result

    def test_with_changes_removed(self) -> None:
        exams: list[ExamInfo] = []
        changes = [
            ExamChange(
                change_type="removed",
                before=_entry("A001", "高数"),
                after=None,
            ),
        ]
        result = build_exam_text_summary(
            exams=exams,
            changes=changes,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "[removed] A001 高数" in result

    def test_with_changes_updated(self) -> None:
        exams = [_exam("A001", "高数上")]
        changes = [
            ExamChange(
                change_type="updated",
                before=_entry("A001", "高数上"),
                after=_entry("A001", "高数上", location="博1-A101"),
            ),
        ]
        result = build_exam_text_summary(
            exams=exams,
            changes=changes,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "[updated]" in result


class TestBuildHtmlReport:
    def test_basic_structure(self) -> None:
        exams = [_exam("A001", "高数", exam_time="2026-06-01(08:00)")]
        html = build_html_report(
            exams=exams,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT 考试报告" in html
        assert "2025-2026 第一学期" in html
        assert "高数" in html
        assert "A001" in html
        assert "2026-06-03T12:00:00" in html

    def test_empty(self) -> None:
        html = build_html_report(
            exams=[],
            year="2025",
            semester="12",
            queried_at="2026-06-03T12:00:00",
        )

        assert "暂无考试安排" in html

    def test_with_changes(self) -> None:
        exams = [_exam("A001", "高数")]
        changes = [
            ExamChange(
                change_type="added",
                before=None,
                after=_entry("A001", "高数"),
            ),
        ]
        html = build_html_report(
            exams=exams,
            changes=changes,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "变更摘要" in html
        assert "新增" in html

    def test_escapes_html_injection(self) -> None:
        exams = [_exam("A001", '<script>alert("xss")</script>')]
        html = build_html_report(
            exams=exams,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "&lt;script&gt;" in html
        assert "<script>" not in html


class TestFormatTermLabel:
    def test_semester_3(self) -> None:
        assert format_term_label("2025", "3") == "2025-2026 第一学期"

    def test_semester_12(self) -> None:
        assert format_term_label("2025", "12") == "2025-2026 第二学期"

    def test_unknown_semester(self) -> None:
        assert format_term_label("2025", "99") == "2025-2026 学期99"

    def test_invalid_year(self) -> None:
        assert format_term_label("unknown", "3") == "unknown-unknown 第一学期"
