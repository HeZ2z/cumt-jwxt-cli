"""Exam list parser tests."""

import pytest

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.exams.parser import parse_exam_list
from cumt_jwxt_cli.models import ExamInfo


def test_parse_exam_list_reads_exam_records() -> None:
    payload = {
        "items": [
            {
                "kch": " M08209 ",
                "kcmc": " 嵌入式系统设计与应用 ",
                "kssj": " 2026-05-06(16:15-17:55) ",
                "cdmc": " 博2-B102 ",
                "cdxqmc": " 南湖校区 ",
                "ksmc": " 2025-2026-2课程考试 ",
                "khfs": " 考试 ",
                "sksj": " 星期二第3-4节{1-6周} ",
                "jsxx": " 李老师 ",
                "xf": " 3.0 ",
            }
        ]
    }

    assert parse_exam_list(payload) == [
        ExamInfo(
            course_code="M08209",
            course_name="嵌入式系统设计与应用",
            exam_time="2026-05-06(16:15-17:55)",
            location="博2-B102",
            campus="南湖校区",
            exam_name="2025-2026-2课程考试",
            exam_method="考试",
            class_schedule="星期二第3-4节{1-6周}",
            teacher_info="李老师",
            credit="3.0",
        )
    ]


@pytest.mark.parametrize("payload", [{}, {"items": {}}, []])
def test_parse_exam_list_rejects_invalid_root_or_items(payload: object) -> None:
    with pytest.raises(ParseError):
        parse_exam_list(payload)


@pytest.mark.parametrize("item", [[], "exam", None])
def test_parse_exam_list_rejects_non_object_item(item: object) -> None:
    with pytest.raises(ParseError):
        parse_exam_list({"items": [item]})


@pytest.mark.parametrize("field", ["kch", "kcmc"])
def test_parse_exam_list_rejects_missing_required_fields(field: str) -> None:
    item = {"kch": "CODE", "kcmc": "Course"}
    del item[field]

    with pytest.raises(ParseError, match=field):
        parse_exam_list({"items": [item]})


@pytest.mark.parametrize("value", [None, 90, [], {}])
def test_parse_exam_list_rejects_non_string_required_fields(value: object) -> None:
    item = {"kch": value, "kcmc": "Course"}

    with pytest.raises(ParseError, match="kch"):
        parse_exam_list({"items": [item]})


@pytest.mark.parametrize("value", ["", "   "])
def test_parse_exam_list_rejects_blank_required_fields(value: str) -> None:
    item = {"kch": "CODE", "kcmc": value}

    with pytest.raises(ParseError, match="kcmc"):
        parse_exam_list({"items": [item]})


def test_parse_exam_list_uses_none_for_missing_optional_fields() -> None:
    exams = parse_exam_list({"items": [{"kch": "CODE", "kcmc": "Course"}]})

    assert exams == [ExamInfo(course_code="CODE", course_name="Course")]


@pytest.mark.parametrize("value", [None, 4.0, [], {}])
def test_parse_exam_list_rejects_non_string_optional_fields(value: object) -> None:
    item = {"kch": "CODE", "kcmc": "Course", "xf": value}

    with pytest.raises(ParseError, match="xf"):
        parse_exam_list({"items": [item]})


def test_parse_exam_list_converts_blank_optional_fields_to_none() -> None:
    exams = parse_exam_list(
        {
            "items": [
                {
                    "kch": "CODE",
                    "kcmc": "Course",
                    "kssj": " ",
                    "cdmc": "",
                    "cdxqmc": " ",
                    "ksmc": "课程考试",
                    "khfs": " ",
                }
            ]
        }
    )

    assert exams == [
        ExamInfo(
            course_code="CODE",
            course_name="Course",
            exam_name="课程考试",
        )
    ]
