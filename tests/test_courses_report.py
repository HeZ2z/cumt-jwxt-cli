"""Course teaching-session report tests."""

from cumt_jwxt_cli.courses.report import build_courses_text_summary
from cumt_jwxt_cli.models import CourseSession


def _session(**overrides: object) -> CourseSession:
    values: dict[str, object] = {
        "course_code": "M12345",
        "course_name": "高等数学",
        "credits": "3.0",
        "total_hours": "48",
        "weekly_hours": "4",
        "course_nature": "必修",
        "teacher_name": "张三",
        "teaching_class": "高数01",
        "class_composition": "计算机2026",
        "class_size": "120",
        "enrolled_count": "60",
        "college": "计算机学院",
        "campus": "南湖校区",
        "building": "博1",
        "room": "A203",
        "weekday": "1",
        "periods": "1-2",
        "start_week": "1-16",
        "schedule_text": "周一第1-2节",
        "location_text": "博1-A203",
    }
    values.update(overrides)
    return CourseSession(**values)  # type: ignore[arg-type]


def test_summary_renders_header_conditions_and_row() -> None:
    text = build_courses_text_summary(
        sessions=[_session()],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert text == "\n".join(
        [
            "CUMT 上课情况 2026-2027 第一学期",
            "条件：教师=张三",
            "共 1 条，显示前 1 条",
            "- 高等数学 | 张三 | 周一 1-2节 | 1-16周 | 博1-A203 | 60/120人 | 3.0学分",
        ]
    )


def test_summary_lists_multiple_conditions() -> None:
    text = build_courses_text_summary(
        sessions=[],
        total=0,
        year="2026",
        semester="12",
        course="M12345",
        weekday=3,
        periods="1-2",
    )

    assert text.splitlines()[0] == "CUMT 上课情况 2026-2027 第二学期"
    assert text.splitlines()[1] == "条件：课程=M12345，星期=周三，节次=1-2"


def test_summary_does_not_double_period_suffix() -> None:
    text = build_courses_text_summary(
        sessions=[_session(periods="3-4节")],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert "| 周一 3-4节 |" in text


def test_summary_deduplicates_repeated_locations() -> None:
    text = build_courses_text_summary(
        sessions=[_session(location_text="博1-A203;博1-A203;博1-B101")],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert "| 博1-A203、博1-B101 |" in text


def test_summary_uses_chinese_weekday() -> None:
    for number, label in enumerate(
        ["周一", "周二", "周三", "周四", "周五", "周六", "周日"], start=1
    ):
        text = build_courses_text_summary(
            sessions=[_session(weekday=str(number))],
            total=1,
            year="2026",
            semester="3",
            teacher="张三",
        )
        assert f"| {label} 1-2节 |" in text


def test_summary_renders_placeholders_for_missing_fields() -> None:
    text = build_courses_text_summary(
        sessions=[
            _session(
                course_name=None,
                teacher_name=None,
                weekday=None,
                periods=None,
                start_week=None,
                location_text=None,
                room=None,
                campus=None,
                building=None,
                enrolled_count=None,
                class_size=None,
                credits=None,
            )
        ],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert text.splitlines()[-1] == "- -- | -- | -- -- | -- | -- | -- | --"


def test_summary_prefers_room_then_campus_building() -> None:
    with_room = build_courses_text_summary(
        sessions=[_session(location_text=None, room="A203")],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )
    composed = build_courses_text_summary(
        sessions=[_session(location_text=None, room=None)],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert "| A203 |" in with_room
    assert "| 南湖校区 博1 |" in composed


def test_summary_formats_people_counts() -> None:
    only_enrolled = build_courses_text_summary(
        sessions=[_session(class_size=None)],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )
    only_size = build_courses_text_summary(
        sessions=[_session(enrolled_count=None)],
        total=1,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert "| 60人 |" in only_enrolled
    assert "| 120人 |" in only_size


def test_summary_renders_empty_result() -> None:
    text = build_courses_text_summary(
        sessions=[],
        total=0,
        year="2026",
        semester="3",
        teacher="张三",
    )

    assert text == "\n".join(
        [
            "CUMT 上课情况 2026-2027 第一学期",
            "条件：教师=张三",
            "未找到符合条件的上课记录。",
        ]
    )
