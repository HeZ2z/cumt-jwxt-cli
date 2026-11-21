"""Class timetable text report tests."""

from cumt_jwxt_cli.class_schedule.report import (
    build_class_schedule_list_text,
    build_class_schedule_text_summary,
    format_week_range,
)
from cumt_jwxt_cli.models import ClassScheduleEntry, ScheduleLesson, ScheduleSlot


def _entry(**overrides: object) -> ClassScheduleEntry:
    values: dict[str, object] = {
        "schedule_code": "T1",
        "schedule_aux": "A1",
        "schedule_name": "课表1",
        "class_id": "0810-202301",
        "class_code": "202301",
        "class_name": "计算机2023-1",
        "major_name": "计算机科学与技术",
        "grade_name": "2023",
        "college_name": "计算机学院",
        "campus": "南湖校区",
        "student_count": "40",
    }
    values.update(overrides)
    return ClassScheduleEntry(**values)  # type: ignore[arg-type]


def _lesson(
    *,
    course_code: str = "M1",
    course_name: str = "高等数学",
    teacher: str | None = "张三",
    weekday: int = 1,
    periods: str = "1-2",
    weeks: tuple[int, ...] = (1, 2, 3),
    location: str | None = "博1-A203",
) -> ScheduleLesson:
    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=None,
        teacher=teacher,
        credits=None,
        course_type=None,
        slots=(
            ScheduleSlot(
                weekday=weekday, periods=periods, weeks=weeks, location=location
            ),
        ),
    )


def test_build_class_schedule_text_summary_formats_lines() -> None:
    text = build_class_schedule_text_summary(
        entry=_entry(),
        lessons=[_lesson()],
        year="2026",
        semester="3",
    )

    assert text.splitlines() == [
        "CUMT 班级课表 2026-2027 第一学期",
        "班级：计算机2023-1（0810-202301）",
        "共 1 个上课时段",
        "- 高等数学 | 张三 | 周一 1-2节 | 1-3周 | 博1-A203",
    ]


def test_build_class_schedule_text_summary_uses_missing_placeholders() -> None:
    text = build_class_schedule_text_summary(
        entry=_entry(class_code=None, class_id=None),
        lessons=[_lesson(teacher=None, location=None)],
        year="2026",
        semester="3",
    )

    assert "班级：计算机2023-1（--）" in text
    assert "- 高等数学 | -- | 周一 1-2节 | 1-3周 | --" in text


def test_build_class_schedule_text_summary_empty_semester() -> None:
    text = build_class_schedule_text_summary(
        entry=_entry(),
        lessons=[],
        year="2026",
        semester="3",
    )

    assert "该班级在所选学期没有课程。" in text


def test_build_class_schedule_text_summary_empty_week() -> None:
    text = build_class_schedule_text_summary(
        entry=_entry(),
        lessons=[],
        year="2026",
        semester="3",
        week=10,
    )

    assert "该周没有课程。" in text


def test_build_class_schedule_text_summary_orders_weekday_labels() -> None:
    lessons = [
        _lesson(course_code="M2", course_name="周二课", weekday=2),
        _lesson(course_code="M1", course_name="周日课", weekday=7),
    ]

    text = build_class_schedule_text_summary(
        entry=_entry(), lessons=lessons, year="2026", semester="3"
    )

    assert "周二 1-2节" in text
    assert "周日 1-2节" in text


def test_format_week_range_compresses_and_deduplicates() -> None:
    assert format_week_range((1, 2, 3, 4, 6, 7, 8)) == "1-4,6-8"
    assert format_week_range((5,)) == "5"
    assert format_week_range(()) == "--"


def test_build_class_schedule_list_text_includes_hint() -> None:
    text = build_class_schedule_list_text(
        entries=[_entry(), _entry(class_name=None, class_code=None)],
        total=2,
    )

    lines = text.splitlines()
    assert lines[0] == "CUMT 班级课表列表"
    assert lines[1] == "匹配 2 个班级课表"
    assert (
        lines[2] == "- 计算机2023-1 | 0810-202301 | 计算机科学与技术 | 2023 | 南湖校区"
    )
    assert lines[-1] == "提示：加 --class 代码查看课表。"


def test_build_class_schedule_list_text_empty() -> None:
    text = build_class_schedule_list_text(entries=[], total=0)

    assert "未找到匹配的班级课表。" in text
