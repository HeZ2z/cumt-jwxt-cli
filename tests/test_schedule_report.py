"""Personal schedule report generation tests."""

from cumt_jwxt_cli.models import (
    PeriodTime,
    ScheduleChange,
    ScheduleLesson,
    ScheduleSlot,
    ScheduleSnapshotEntry,
)
from cumt_jwxt_cli.schedule.report import (
    build_html_report,
    build_schedule_text_summary,
    format_term_label,
    format_weeks,
)

_PERIOD_TIMES = (
    PeriodTime(period="1", start="08:00", end="08:50"),
    PeriodTime(period="2", start="08:55", end="09:45"),
    PeriodTime(period="3", start="10:15", end="11:05"),
)


def _slot(
    weekday: int = 1,
    periods: str = "1-2",
    weeks: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8),
    location: str | None = "教一A101",
) -> ScheduleSlot:
    return ScheduleSlot(
        weekday=weekday, periods=periods, weeks=weeks, location=location
    )


def _lesson(
    course_code: str = "A001",
    course_name: str = "高等数学",
    *,
    teaching_class: str | None = "01班",
    teacher: str | None = "张三",
    credits: str | None = "5.0",
    course_type: str | None = "必修",
    slots: tuple[ScheduleSlot, ...] | None = None,
) -> ScheduleLesson:
    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=teaching_class,
        teacher=teacher,
        credits=credits,
        course_type=course_type,
        slots=slots if slots is not None else (_slot(),),
    )


def _entry(
    course_code: str = "A001",
    course_name: str = "高等数学",
    *,
    teacher: str | None = "张三",
    slots: tuple[ScheduleSlot, ...] | None = None,
) -> ScheduleSnapshotEntry:
    return ScheduleSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        teaching_class="01班",
        teacher=teacher,
        slots=slots if slots is not None else (_slot(),),
    )


class TestFormatTermLabel:
    def test_semester_3(self) -> None:
        assert format_term_label("2025", "3") == "2025-2026 第一学期"

    def test_semester_12(self) -> None:
        assert format_term_label("2025", "12") == "2025-2026 第二学期"

    def test_unknown_semester(self) -> None:
        assert format_term_label("2025", "99") == "2025-2026 学期99"

    def test_invalid_year(self) -> None:
        assert format_term_label("unknown", "3") == "unknown-unknown 第一学期"


class TestFormatWeeks:
    def test_contiguous_range(self) -> None:
        assert format_weeks((1, 2, 3, 4, 5)) == "第1-5周"

    def test_multiple_ranges(self) -> None:
        assert (
            format_weeks(tuple(range(1, 9)) + tuple(range(10, 17))) == "第1-8,10-16周"
        )

    def test_single_week(self) -> None:
        assert format_weeks((4,)) == "第4周"

    def test_empty(self) -> None:
        assert format_weeks(()) == ""


class TestBuildScheduleTextSummary:
    def test_with_lessons(self) -> None:
        lessons = [
            _lesson(
                course_code="A001",
                course_name="高等数学",
                slots=(_slot(weekday=1, periods="1-2"),),
            ),
            _lesson(
                course_code="B002",
                course_name="大学英语",
                teacher="李四",
                credits="3.0",
                course_type="选修",
                slots=(_slot(weekday=3, periods="5-6", location="博2-B102"),),
            ),
        ]
        result = build_schedule_text_summary(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT 课表 2025-2026 第一学期" in result
        assert "查询时间：2026-06-03T12:00:00" in result
        assert "课程数量：2" in result
        assert "1. 高等数学 (A001)" in result
        assert "2. 大学英语 (B002)" in result
        assert "周一 1-2节 第1-8周 教一A101" in result
        assert "周三 5-6节 第1-8周 博2-B102" in result
        assert "李四" in result

    def test_empty(self) -> None:
        result = build_schedule_text_summary(
            lessons=[],
            year="2025",
            semester="12",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT 课表 2025-2026 第二学期" in result
        assert "课程数量：0" in result
        assert "本学期暂无课程安排。" in result

    def test_lesson_slot_lines_include_clock_times(self) -> None:
        lessons = [_lesson(slots=(_slot(weekday=1, periods="1-2"),))]
        result = build_schedule_text_summary(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert "周一 1-2节 08:00-09:45 第1-8周 教一A101" in result

    def test_single_period_uses_its_own_start_and_end(self) -> None:
        lessons = [_lesson(slots=(_slot(weekday=1, periods="3"),))]
        result = build_schedule_text_summary(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert "周一 3节 10:15-11:05" in result

    def test_lesson_slot_lines_fall_back_without_period_times(self) -> None:
        lessons = [_lesson(slots=(_slot(weekday=1, periods="1-2"),))]
        result = build_schedule_text_summary(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "周一 1-2节 第1-8周 教一A101" in result
        assert "08:00" not in result

    def test_lesson_slot_lines_fall_back_when_periods_unmapped(self) -> None:
        lessons = [_lesson(slots=(_slot(weekday=1, periods="7-8"),))]
        result = build_schedule_text_summary(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert "周一 7-8节 第1-8周" in result

    def test_added_change_includes_clock_times(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(course_name="高等数学"),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert (
            "新增课程：高等数学（周一 1-2节 08:00-09:45，第1-8周，教一A101，张三）"
            in result
        )

    def test_time_change_includes_clock_times_on_both_sides(self) -> None:
        changes = [
            ScheduleChange(
                change_type="updated",
                before=_entry(
                    course_name="线性代数",
                    slots=(_slot(weekday=2, periods="1-2"),),
                ),
                after=_entry(
                    course_name="线性代数",
                    slots=(_slot(weekday=2, periods="3"),),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert (
            "时间变更：线性代数 周二 1-2节 08:00-09:45 → 周二 3节 10:15-11:05" in result
        )

    def test_added_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(
                    course_name="高等数学",
                    slots=(
                        _slot(
                            weekday=1,
                            periods="1-2",
                            weeks=tuple(range(1, 17)),
                            location="教一A101",
                        ),
                    ),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "新增课程：高等数学（周一 1-2节，第1-16周，教一A101，张三）" in result

    def test_removed_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="removed",
                before=_entry(
                    course_name="大学物理",
                    slots=(_slot(weekday=3, periods="5-6"),),
                ),
                after=None,
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "删除课程：大学物理（周三 5-6节，教一A101）" in result

    def test_added_change_with_differing_slot_locations(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(
                    course_name="算法导论",
                    slots=(
                        _slot(weekday=1, periods="5-6", location="博1-A203"),
                        _slot(weekday=1, periods="5-6", location="博1-B101"),
                        _slot(weekday=3, periods="5-8", location="博1-C101"),
                    ),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert (
            "新增课程：算法导论（周一 5-6节@博1-A203、周一 5-6节@博1-B101、"
            "周三 5-8节@博1-C101，第1-8周，张三）"
        ) in result

    def test_added_change_with_shared_location_prints_location_once(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(
                    course_name="离散数学",
                    slots=(
                        _slot(weekday=1, periods="1-2", location="教一A101"),
                        _slot(weekday=3, periods="3-4", location="教一A101"),
                    ),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert (
            "新增课程：离散数学（周一 1-2节、周三 3-4节，第1-8周，教一A101，张三）"
        ) in result

    def test_removed_change_with_differing_slot_locations(self) -> None:
        changes = [
            ScheduleChange(
                change_type="removed",
                before=_entry(
                    course_name="算法导论",
                    slots=(
                        _slot(weekday=1, periods="5-6", location="博1-A203"),
                        _slot(weekday=3, periods="5-8", location="博1-C101"),
                    ),
                ),
                after=None,
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert (
            "删除课程：算法导论（周一 5-6节@博1-A203、周三 5-8节@博1-C101）"
        ) in result

    def test_time_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="updated",
                before=_entry(
                    course_name="线性代数",
                    slots=(_slot(weekday=2, periods="3-4"),),
                ),
                after=_entry(
                    course_name="线性代数",
                    slots=(_slot(weekday=2, periods="5-6"),),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "时间变更：线性代数 周二 3-4节 → 周二 5-6节" in result

    def test_location_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="updated",
                before=_entry(
                    course_name="程序设计",
                    slots=(_slot(location="实验楼B203"),),
                ),
                after=_entry(
                    course_name="程序设计",
                    slots=(_slot(location="实验楼B305"),),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "教室变更：程序设计 实验楼B203 → 实验楼B305" in result

    def test_weeks_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="updated",
                before=_entry(
                    course_name="英语",
                    slots=(_slot(weeks=tuple(range(1, 9))),),
                ),
                after=_entry(
                    course_name="英语",
                    slots=(_slot(weeks=tuple(range(1, 9)) + tuple(range(10, 17))),),
                ),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "周次变更：英语 第1-8周 → 第1-8,10-16周" in result

    def test_teacher_change_description(self) -> None:
        changes = [
            ScheduleChange(
                change_type="updated",
                before=_entry(course_name="概率论", teacher="李四"),
                after=_entry(course_name="概率论", teacher="王五"),
            )
        ]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "教师变更：概率论 李四 → 王五" in result

    def test_slot_order_does_not_affect_change_detection(self) -> None:
        before = _entry(
            slots=(_slot(weekday=1), _slot(weekday=3, periods="3-4")),
        )
        after = _entry(
            slots=(_slot(weekday=3, periods="3-4"), _slot(weekday=1)),
        )
        changes = [ScheduleChange(change_type="updated", before=before, after=after)]
        result = build_schedule_text_summary(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "时间变更" not in result


class TestBuildHtmlReport:
    def test_basic_structure(self) -> None:
        lessons = [_lesson(course_code="A001", course_name="高等数学")]
        html = build_html_report(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="2026-06-03T12:00:00",
        )

        assert "CUMT 个人课表报告" in html
        assert "2025-2026 第一学期" in html
        assert "高等数学" in html
        assert "A001" in html
        assert "2026-06-03T12:00:00" in html

    def test_empty(self) -> None:
        html = build_html_report(
            lessons=[],
            year="2025",
            semester="12",
            queried_at="2026-06-03T12:00:00",
        )

        assert "本学期暂无课程安排" in html

    def test_lesson_slot_times_include_clock_times(self) -> None:
        lessons = [_lesson(slots=(_slot(weekday=1, periods="1-2"),))]
        html = build_html_report(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert "周一 1-2节 08:00-09:45" in html

    def test_change_lines_include_clock_times(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(course_name="高等数学"),
            )
        ]
        html = build_html_report(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
            period_times=_PERIOD_TIMES,
        )

        assert "新增课程：高等数学（周一 1-2节 08:00-09:45" in html

    def test_with_changes(self) -> None:
        changes = [
            ScheduleChange(
                change_type="added",
                before=None,
                after=_entry(course_name="高等数学"),
            )
        ]
        html = build_html_report(
            lessons=[],
            changes=changes,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "变更摘要" in html
        assert "新增" in html
        assert "新增课程：高等数学" in html

    def test_escapes_html_injection(self) -> None:
        lessons = [_lesson(course_code="A001", course_name="<script>x</script>")]
        html = build_html_report(
            lessons=lessons,
            year="2025",
            semester="3",
            queried_at="t",
        )

        assert "&lt;script&gt;" in html
        assert "<script>" not in html
