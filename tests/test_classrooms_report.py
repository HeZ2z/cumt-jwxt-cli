"""Free classroom report tests."""

from cumt_jwxt_cli.classrooms.report import build_classrooms_text_summary
from cumt_jwxt_cli.models import FreeClassroom


def _room(**overrides: object) -> FreeClassroom:
    values: dict[str, object] = {
        "room_name": "博1-A203",
        "room_code": "A203",
        "building": "博1",
        "floor": "2",
        "campus": "南湖校区",
        "category": "公用多媒体",
        "seats": "170",
        "exam_seats": "165",
        "lendable": True,
        "schedulable": True,
    }
    values.update(overrides)
    return FreeClassroom(**values)  # type: ignore[arg-type]


def test_summary_renders_header_count_and_room_line() -> None:
    text = build_classrooms_text_summary(
        classrooms=[_room()],
        total=559,
        date="2026-11-23",
        start="08:00",
        end="09:40",
        campus="nanhu",
    )

    assert text == "\n".join(
        [
            "CUMT 空闲教室 2026-11-23 08:00-09:40（南湖校区）",
            "共 559 间，显示前 1 间",
            "- 博1-A203 | 博1 2层 | 170座 | 公用多媒体 | 可借用",
        ]
    )


def test_summary_omits_time_window_when_absent() -> None:
    text = build_classrooms_text_summary(
        classrooms=[_room()],
        total=1,
        date="2026-11-23",
        campus="all",
    )

    assert text.splitlines()[0] == "CUMT 空闲教室 2026-11-23（全部校区）"
    assert text.splitlines()[1] == "共 1 间"


def test_summary_renders_empty_result() -> None:
    text = build_classrooms_text_summary(
        classrooms=[],
        total=0,
        date="2026-11-23",
        start="08:00",
        end="09:40",
        campus="wenchang",
    )

    assert text == "\n".join(
        [
            "CUMT 空闲教室 2026-11-23 08:00-09:40（文昌校区）",
            "未找到符合条件的空闲教室。",
        ]
    )


def test_summary_uses_placeholders_for_missing_fields() -> None:
    text = build_classrooms_text_summary(
        classrooms=[
            _room(
                room_name=None,
                room_code=None,
                building=None,
                floor=None,
                category=None,
                seats=None,
                lendable=None,
            )
        ],
        total=1,
        date="2026-11-23",
    )

    assert text.splitlines()[-1] == "- -- | -- -- | -- | -- | --"


def test_summary_marks_not_lendable() -> None:
    text = build_classrooms_text_summary(
        classrooms=[_room(lendable=False, room_code="A203")],
        total=1,
        date="2026-11-23",
    )

    assert text.splitlines()[-1].endswith("不可借用")
