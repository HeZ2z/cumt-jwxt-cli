"""Schedule ICS calendar generation tests."""

from datetime import date

from cumt_jwxt_cli.models import PeriodTime, ScheduleLesson, ScheduleSlot
from cumt_jwxt_cli.schedule.ics import (
    build_ics_content,
    build_ics_filename,
    split_week_runs,
)

_PERIOD_TIMES = (
    PeriodTime(period="1", start="08:00", end="08:50", section="上午"),
    PeriodTime(period="2", start="08:55", end="09:45", section="上午"),
    PeriodTime(period="3", start="10:15", end="11:05", section="上午"),
    PeriodTime(period="4", start="11:10", end="12:00", section="上午"),
)

# Mondays for weeks 1, 2, 3, 5 and 7 in the 2025 fall semester.
_WEEK_DATES = {
    1: date(2025, 9, 1),
    2: date(2025, 9, 8),
    3: date(2025, 9, 15),
    5: date(2025, 9, 29),
    7: date(2025, 10, 13),
}


def _lesson(**overrides: object) -> ScheduleLesson:
    values: dict[str, object] = {
        "course_code": "A001",
        "course_name": "高等数学",
        "teaching_class": "01班",
        "teacher": "张老师",
        "credits": "5.0",
        "course_type": "必修",
        "slots": (
            ScheduleSlot(
                weekday=1,
                periods="1-2",
                weeks=(1, 2, 3),
                location="博1-A101",
            ),
        ),
    }
    values.update(overrides)
    return ScheduleLesson(**values)  # type: ignore[arg-type]


def _content(lesson: ScheduleLesson) -> str:
    return build_ics_content((lesson,), _PERIOD_TIMES, _WEEK_DATES, "2025", "3")


class TestBuildIcsFilename:
    def test_fall_filename(self) -> None:
        assert build_ics_filename("2025", "3") == "schedule_25fa.ics"

    def test_spring_filename(self) -> None:
        assert build_ics_filename("2025", "12") == "schedule_25sp.ics"


class TestSplitWeekRuns:
    def test_contiguous_run(self) -> None:
        assert split_week_runs((1, 2, 3)) == [((1, 2, 3), 1)]

    def test_pure_odd_run(self) -> None:
        assert split_week_runs((1, 3, 5)) == [((1, 3, 5), 2)]

    def test_splits_mixed_intervals(self) -> None:
        assert split_week_runs((1, 2, 3, 5, 7)) == [
            ((1, 2, 3), 1),
            ((5, 7), 2),
        ]

    def test_splits_when_interval_changes(self) -> None:
        assert split_week_runs((1, 2, 4, 5)) == [((1, 2), 1), ((4, 5), 1)]

    def test_single_week(self) -> None:
        assert split_week_runs((4,)) == [((4,), 1)]

    def test_sorts_and_deduplicates(self) -> None:
        assert split_week_runs((3, 1, 2, 2)) == [((1, 2, 3), 1)]

    def test_empty(self) -> None:
        assert split_week_runs(()) == []


class TestBuildIcsContent:
    def test_header_and_prodid(self) -> None:
        content = _content(_lesson())

        assert "BEGIN:VCALENDAR" in content
        assert "VERSION:2.0" in content
        assert "PRODID:-//cumt-jwxt-cli//Schedule//EN" in content
        assert "END:VCALENDAR" in content

    def test_includes_timezone(self) -> None:
        content = _content(_lesson())

        assert "TZID:Asia/Shanghai" in content
        assert "TZNAME:CST" in content
        assert "TZOFFSETFROM:+0800" in content
        assert "TZOFFSETTO:+0800" in content
        assert "DTSTART:19700101T000000" in content
        assert "X-LIC-LOCATION:Asia/Shanghai" in content

    def test_dtstart_and_dtend(self) -> None:
        content = _content(_lesson())

        assert "DTSTART;TZID=Asia/Shanghai:20250901T080000" in content
        assert "DTEND;TZID=Asia/Shanghai:20250901T094500" in content

    def test_rrule_for_contiguous_run(self) -> None:
        content = _content(_lesson())

        assert "RRULE:FREQ=WEEKLY;INTERVAL=1;UNTIL=20250921T160000Z" in content

    def test_rrule_for_odd_run(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(
                    weekday=1,
                    periods="1-2",
                    weeks=(1, 3, 5),
                    location="博1-A101",
                ),
            )
        )
        content = _content(lesson)

        assert "RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=20251012T160000Z" in content

    def test_splits_multiple_events_per_week_run(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(
                    weekday=1,
                    periods="1-2",
                    weeks=(1, 2, 3, 5, 7),
                    location="博1-A101",
                ),
            )
        )
        content = _content(lesson)

        assert content.count("BEGIN:VEVENT") == 2
        assert "INTERVAL=1;UNTIL=20250921T160000Z" in content
        assert "INTERVAL=2;UNTIL=20251026T160000Z" in content

    def test_uid_prefix_and_determinism(self) -> None:
        first = _content(_lesson())
        second = _content(_lesson())

        uids = [line for line in first.splitlines() if line.startswith("UID:")]
        assert uids
        assert uids[0].startswith("UID:cumt-jwxt-schedule-")
        assert [line for line in second.splitlines() if line.startswith("UID:")] == uids

    def test_summary_location_description(self) -> None:
        content = _content(_lesson())

        assert "SUMMARY:高等数学" in content
        assert "LOCATION:博1-A101 张老师" in content
        assert "DESCRIPTION:第1 - 2节\\n博1-A101\\n张老师" in content

    def test_location_omits_missing_teacher(self) -> None:
        content = _content(_lesson(teacher=None))

        assert "LOCATION:博1-A101" in content
        assert "LOCATION:博1-A101 " not in content

    def test_valarm(self) -> None:
        content = _content(_lesson())

        assert "BEGIN:VALARM" in content
        assert "ACTION:DISPLAY" in content
        assert "TRIGGER;RELATED=START:-PT20M" in content
        assert "DESCRIPTION:高等数学@博1-A101\\n" in content
        assert "END:VALARM" in content

    def test_skips_slot_without_weeks(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(weekday=1, periods="1-2", weeks=(), location="博1-A101"),
            )
        )

        assert "BEGIN:VEVENT" not in _content(lesson)

    def test_skips_slot_with_unparseable_periods(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(
                    weekday=1,
                    periods="bad",
                    weeks=(1, 2, 3),
                    location="博1-A101",
                ),
            )
        )

        assert "BEGIN:VEVENT" not in _content(lesson)

    def test_skips_slot_with_missing_period_times(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(
                    weekday=1,
                    periods="7-8",
                    weeks=(1, 2, 3),
                    location="博1-A101",
                ),
            )
        )

        assert "BEGIN:VEVENT" not in _content(lesson)

    def test_skips_slot_with_missing_week_dates(self) -> None:
        lesson = _lesson(
            slots=(
                ScheduleSlot(
                    weekday=1,
                    periods="1-2",
                    weeks=(9,),
                    location="博1-A101",
                ),
            )
        )

        assert "BEGIN:VEVENT" not in _content(lesson)

    def test_multiple_lessons(self) -> None:
        lessons = (
            _lesson(course_code="A001", course_name="高数"),
            _lesson(course_code="B002", course_name="英语"),
        )
        content = build_ics_content(lessons, _PERIOD_TIMES, _WEEK_DATES, "2025", "3")

        assert content.count("BEGIN:VEVENT") == 2
