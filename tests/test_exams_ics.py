"""ICS calendar generation tests."""

from cumt_jwxt_cli.exams.ics import (
    build_ics_content,
    build_ics_filename,
    short_year_semester,
)
from cumt_jwxt_cli.models import ExamInfo


def _exam(**overrides: str) -> ExamInfo:
    values = {
        "course_code": "M08209",
        "course_name": "嵌入式系统设计与应用",
        "exam_time": "2026-05-06(16:15-17:55)",
        "location": "博2-B102",
        "campus": "南湖校区",
        "exam_name": "2025-2026-2课程考试",
        "exam_method": "考试",
    }
    values.update(overrides)
    return ExamInfo(**values)


class TestShortYearSemester:
    def test_fall_semester(self) -> None:
        assert short_year_semester("2026", "3") == "26fa"

    def test_spring_semester(self) -> None:
        assert short_year_semester("2026", "12") == "26sp"

    def test_single_digit_year(self) -> None:
        assert short_year_semester("5", "3") == "5fa"


class TestBuildIcsFilename:
    def test_filename_format(self) -> None:
        assert build_ics_filename("2026", "12") == "exam_schedule_26sp.ics"

    def test_fall_filename(self) -> None:
        assert build_ics_filename("2026", "3") == "exam_schedule_26fa.ics"


class TestBuildIcsContent:
    def test_generates_valid_ics_header(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "BEGIN:VCALENDAR" in content
        assert "VERSION:2.0" in content
        assert "END:VCALENDAR" in content

    def test_includes_timezone(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "TZID:Asia/Shanghai" in content
        assert "X-LIC-LOCATION:Asia/Shanghai" in content

    def test_includes_x_wr_calname(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "X-WR-CALNAME" in content
        assert "CUMT 考试安排" in content

    def test_vevent_fields(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "BEGIN:VEVENT" in content
        assert "END:VEVENT" in content
        assert "SUMMARY:嵌入式系统设计与应用 2025-2026-2课程考试" in content
        assert "LOCATION:博2-B102" in content
        assert "DESCRIPTION:M08209" in content

    def test_dtstart_dtend_with_tzid(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "DTSTART;TZID=Asia/Shanghai:20260506T161500" in content
        assert "DTEND;TZID=Asia/Shanghai:20260506T175500" in content

    def test_deterministic_uid(self) -> None:
        content1 = build_ics_content((_exam(),), "2026", "12")
        content2 = build_ics_content((_exam(),), "2026", "12")
        uid1 = ""
        uid2 = ""
        for line in content1.splitlines():
            if line.startswith("UID:"):
                uid1 = line
        for line in content2.splitlines():
            if line.startswith("UID:"):
                uid2 = line
        assert uid1 and uid2
        assert uid1 == uid2

    def test_no_valarm(self) -> None:
        content = build_ics_content((_exam(),), "2026", "12")
        assert "VALARM" not in content

    def test_summary_falls_back_to_course_name(self) -> None:
        exam = _exam(exam_name="")
        content = build_ics_content((exam,), "2026", "12")
        assert "SUMMARY:嵌入式系统设计与应用" in content

    def test_multiple_exams(self) -> None:
        exams = (
            _exam(
                course_code="A001",
                course_name="高数",
                exam_time="2026-06-01(08:00-10:00)",
                exam_name="期末考试",
            ),
            _exam(
                course_code="B002",
                course_name="英语",
                exam_time="2026-06-03(14:00-16:00)",
                exam_name="期末考试",
            ),
        )
        content = build_ics_content(exams, "2026", "12")
        assert content.count("BEGIN:VEVENT") == 2
        assert content.count("END:VEVENT") == 2

    def test_skips_exam_without_exam_time(self) -> None:
        exam = _exam(exam_time=None)  # type: ignore[arg-type]
        content = build_ics_content((exam,), "2026", "12")
        assert "BEGIN:VEVENT" not in content

    def test_skips_exam_with_unparseable_exam_time(self) -> None:
        exam = _exam(exam_time="invalid-format")
        content = build_ics_content((exam,), "2026", "12")
        assert "BEGIN:VEVENT" not in content

    def test_description_format(self) -> None:
        exam = _exam(
            course_code="M08209",
            campus="南湖校区",
            location="博2-B102",
            exam_method="考试",
        )
        content = build_ics_content((exam,), "2026", "12")
        assert "DESCRIPTION:M08209\\n南湖校区\\n博2-B102\\n考试" in content

    def test_description_minimal_without_optionals(self) -> None:
        exam = ExamInfo(
            course_code="A001", course_name="高数", exam_time="2026-06-01(08:00-09:00)"
        )
        content = build_ics_content((exam,), "2026", "12")
        assert "DESCRIPTION:A001" in content
