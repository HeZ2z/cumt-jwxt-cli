"""Schedule parser tests."""

from datetime import date

import pytest

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.models import (
    PeriodTime,
    ScheduleLesson,
    ScheduleSlot,
    ScheduleUnscheduledCourse,
)
from cumt_jwxt_cli.schedule.parser import (
    parse_period_times,
    parse_schedule_payload,
    parse_week_dates,
    parse_week_ranges,
)


class TestParseWeekRanges:
    def test_expands_multiple_ranges(self) -> None:
        assert parse_week_ranges("1-5周,7-10周,12-13周") == (
            1,
            2,
            3,
            4,
            5,
            7,
            8,
            9,
            10,
            12,
            13,
        )

    def test_odd_parity_suffix(self) -> None:
        assert parse_week_ranges("1-6周(单)") == (1, 3, 5)

    def test_even_parity_suffix(self) -> None:
        assert parse_week_ranges("1-6周(双)") == (2, 4, 6)

    def test_single_week(self) -> None:
        assert parse_week_ranges("3周") == (3,)

    def test_deduplicates_overlapping_ranges(self) -> None:
        assert parse_week_ranges("1-2周,2-3周") == (1, 2, 3)

    def test_tolerates_whitespace(self) -> None:
        assert parse_week_ranges(" 1-2周 , 4周 ") == (1, 2, 4)

    @pytest.mark.parametrize("value", ["", "   ", "abc", "1-2", "1-2周,abc"])
    def test_rejects_unsupported_values(self, value: str) -> None:
        with pytest.raises(ParseError):
            parse_week_ranges(value)

    def test_rejects_reversed_range(self) -> None:
        with pytest.raises(ParseError, match="reversed"):
            parse_week_ranges("5-3周")


class TestParseSchedulePayload:
    def test_reads_lessons_and_unscheduled(self) -> None:
        payload = {
            "kbList": [
                {
                    "kcmc": " 高等数学 ",
                    "xm": " 张老师 ",
                    "cdmc": " 博1-A101 ",
                    "kch_id": " M001 ",
                    "kch": " LEGACY ",
                    "jxbmc": " 高数01班 ",
                    "jxb_id": " JXB-1 ",
                    "xf": " 5.0 ",
                    "xqj": "1",
                    "jcs": "1-2",
                    "zcd": "1-5周,7-8周",
                    "kclbmc": " 必修 ",
                    "khfsmc": " 闭卷 ",
                }
            ],
            "sjkList": [
                {"kcmc": " 实践课 ", "jsxm": " 李老师 ", "qsjsz": "1-4", "xf": "1.0"}
            ],
            "qsxqj": 1,
        }

        result = parse_schedule_payload(payload)

        assert result.lessons == (
            ScheduleLesson(
                course_code="M001",
                course_name="高等数学",
                teaching_class="高数01班",
                teacher="张老师",
                credits="5.0",
                course_type="必修",
                slots=(
                    ScheduleSlot(
                        weekday=1,
                        periods="1-2",
                        weeks=(1, 2, 3, 4, 5, 7, 8),
                        location="博1-A101",
                    ),
                ),
            ),
        )
        assert result.unscheduled == (
            ScheduleUnscheduledCourse(
                course_name="实践课",
                teacher="李老师",
                week_range="1-4",
                credits="1.0",
            ),
        )

    def test_falls_back_to_jc_when_jcs_missing(self) -> None:
        payload = {
            "kbList": [
                {
                    "kcmc": "高数",
                    "kch": "M001",
                    "xqj": "3",
                    "jc": "5-6",
                    "zcd": "1周",
                }
            ]
        }

        lesson = parse_schedule_payload(payload).lessons[0]
        assert lesson.slots[0].periods == "5-6"

    def test_missing_optional_fields_become_none(self) -> None:
        payload = {
            "kbList": [
                {"kcmc": "高数", "kch": "M001", "xqj": "1", "jcs": "1", "zcd": "1周"}
            ]
        }

        lesson = parse_schedule_payload(payload).lessons[0]
        assert lesson.teaching_class is None
        assert lesson.teacher is None
        assert lesson.credits is None
        assert lesson.course_type is None
        assert lesson.slots[0].location is None

    def test_accepts_integer_weekday(self) -> None:
        payload = {
            "kbList": [
                {"kcmc": "高数", "kch": "M001", "xqj": 2, "jcs": "1", "zcd": "1周"}
            ]
        }

        assert parse_schedule_payload(payload).lessons[0].slots[0].weekday == 2

    @pytest.mark.parametrize("payload", [{}, {"kbList": {}}, []])
    def test_rejects_invalid_root_or_kb_list(self, payload: object) -> None:
        with pytest.raises(ParseError):
            parse_schedule_payload(payload)

    def test_rejects_non_list_sjk_list(self) -> None:
        with pytest.raises(ParseError, match="sjkList"):
            parse_schedule_payload({"kbList": [], "sjkList": {}})

    @pytest.mark.parametrize("item", [[], "lesson", None])
    def test_rejects_non_object_lesson(self, item: object) -> None:
        with pytest.raises(ParseError):
            parse_schedule_payload({"kbList": [item]})

    def test_rejects_missing_course_code(self) -> None:
        item = {"kcmc": "高数", "xqj": "1", "jcs": "1", "zcd": "1周"}
        with pytest.raises(ParseError, match="kch_id or kch"):
            parse_schedule_payload({"kbList": [item]})

    def test_rejects_missing_course_name(self) -> None:
        item = {"kch": "M001", "xqj": "1", "jcs": "1", "zcd": "1周"}
        with pytest.raises(ParseError, match="kcmc"):
            parse_schedule_payload({"kbList": [item]})

    @pytest.mark.parametrize("weekday", ["0", "8", "abc"])
    def test_rejects_invalid_weekday(self, weekday: str) -> None:
        item = {"kcmc": "高数", "kch": "M001", "xqj": weekday, "jcs": "1", "zcd": "1周"}
        with pytest.raises(ParseError):
            parse_schedule_payload({"kbList": [item]})

    def test_rejects_invalid_week_string(self) -> None:
        item = {"kcmc": "高数", "kch": "M001", "xqj": "1", "jcs": "1", "zcd": "bad"}
        with pytest.raises(ParseError):
            parse_schedule_payload({"kbList": [item]})


class TestParsePeriodTimes:
    def test_reads_period_times(self) -> None:
        payload = [
            {"jcmc": "1", "qssj": "08:00", "jssj": "08:50", "rsdmc": "上午"},
            {"jcmc": "2", "qssj": "08:55", "jssj": "09:45"},
        ]

        assert parse_period_times(payload) == (
            PeriodTime(period="1", start="08:00", end="08:50", section="上午"),
            PeriodTime(period="2", start="08:55", end="09:45"),
        )

    @pytest.mark.parametrize("payload", [{}, "periods", None])
    def test_rejects_non_list_root(self, payload: object) -> None:
        with pytest.raises(ParseError):
            parse_period_times(payload)

    def test_rejects_missing_period_fields(self) -> None:
        with pytest.raises(ParseError, match="qssj"):
            parse_period_times([{"jcmc": "1", "jssj": "08:50"}])


class TestParseWeekDates:
    def test_extracts_monday_dates_with_chinese_separator(self) -> None:
        payload = [
            {
                "zs": "1",
                "zsmc": "1",
                "zcrq": "1(2025-09-01至2025-09-07)",
                "zcrq2": "1(2025-09-01至2025-09-07)",
            },
            {"zs": "2", "zcrq": "2(2025-09-08至2025-09-14)"},
        ]

        assert parse_week_dates(payload) == {
            1: date(2025, 9, 1),
            2: date(2025, 9, 8),
        }

    def test_regression_chinese_separator_returns_non_empty_mapping(self) -> None:
        # Live CUMT payloads use 至 (U+81F3), not '~'. A previous pattern only
        # matched '~', so this returned {} and every ICS slot was skipped.
        payload = [{"zs": "1", "zcrq": "1(2025-09-01至2025-09-07)"}]

        assert parse_week_dates(payload) == {1: date(2025, 9, 1)}

    def test_tolerates_ascii_tilde_separator(self) -> None:
        payload = [{"zs": "1", "zcrq": "1(2025-09-01~2025-09-07)"}]

        assert parse_week_dates(payload) == {1: date(2025, 9, 1)}

    def test_uses_first_date_as_monday(self) -> None:
        payload = [{"zs": "3", "zcrq": "3(2025-09-15至2025-09-21)"}]

        assert parse_week_dates(payload)[3] == date(2025, 9, 15)

    def test_skips_items_without_parseable_range(self) -> None:
        payload = [{"zs": "1", "zcrq": "not-a-range"}]

        assert parse_week_dates(payload) == {}

    @pytest.mark.parametrize("payload", [{}, "weeks", None])
    def test_rejects_non_list_root(self, payload: object) -> None:
        with pytest.raises(ParseError):
            parse_week_dates(payload)

    def test_rejects_invalid_week_number(self) -> None:
        with pytest.raises(ParseError, match="zs"):
            parse_week_dates([{"zs": "x", "zcrq": "1(2025-09-01~2025-09-07)"}])
