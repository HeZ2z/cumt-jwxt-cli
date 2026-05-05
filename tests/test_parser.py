"""Grade list parser tests."""

import pytest

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.grades.parser import parse_grade_list
from cumt_jwxt_cli.models import CourseGrade


def test_parse_grade_list_reads_course_grades() -> None:
    payload = {
        "items": [
            {
                "kch": " MATH101 ",
                "kcmc": " 高等数学 ",
                "cj": " 95 ",
                "xf": " 4.0 ",
                "jd": " 4.5 ",
                "kcxzmc": " 必修 ",
                "khfsmc": " 考试 ",
                "jxb_id": " JXB-1 ",
            }
        ]
    }

    assert parse_grade_list(payload) == [
        CourseGrade(
            course_code="MATH101",
            course_name="高等数学",
            score="95",
            credit="4.0",
            grade_point="4.5",
            course_type="必修",
            exam_type="考试",
            teaching_class_id="JXB-1",
        )
    ]


@pytest.mark.parametrize("payload", [{}, {"items": {}}, []])
def test_parse_grade_list_rejects_invalid_root_or_items(payload: object) -> None:
    with pytest.raises(ParseError):
        parse_grade_list(payload)


@pytest.mark.parametrize("item", [[], "course", None])
def test_parse_grade_list_rejects_non_object_item(item: object) -> None:
    with pytest.raises(ParseError):
        parse_grade_list({"items": [item]})


@pytest.mark.parametrize("field", ["kch", "kcmc", "cj"])
def test_parse_grade_list_rejects_missing_required_fields(field: str) -> None:
    item = {"kch": "CODE", "kcmc": "Course", "cj": "90"}
    del item[field]

    with pytest.raises(ParseError, match=field):
        parse_grade_list({"items": [item]})


@pytest.mark.parametrize("value", [None, 90, [], {}])
def test_parse_grade_list_rejects_non_string_required_fields(value: object) -> None:
    item = {"kch": value, "kcmc": "Course", "cj": "90"}

    with pytest.raises(ParseError, match="kch"):
        parse_grade_list({"items": [item]})


@pytest.mark.parametrize("value", ["", "   "])
def test_parse_grade_list_rejects_blank_required_fields(value: str) -> None:
    item = {"kch": "CODE", "kcmc": value, "cj": "90"}

    with pytest.raises(ParseError, match="kcmc"):
        parse_grade_list({"items": [item]})


def test_parse_grade_list_uses_none_for_missing_optional_fields() -> None:
    grades = parse_grade_list(
        {"items": [{"kch": "CODE", "kcmc": "Course", "cj": "90"}]}
    )

    assert grades == [CourseGrade(course_code="CODE", course_name="Course", score="90")]


@pytest.mark.parametrize("value", [None, 4.0, [], {}])
def test_parse_grade_list_rejects_non_string_optional_fields(value: object) -> None:
    item = {"kch": "CODE", "kcmc": "Course", "cj": "90", "xf": value}

    with pytest.raises(ParseError, match="xf"):
        parse_grade_list({"items": [item]})


def test_parse_grade_list_converts_blank_optional_fields_to_none() -> None:
    grades = parse_grade_list(
        {
            "items": [
                {
                    "kch": "CODE",
                    "kcmc": "Course",
                    "cj": "90",
                    "xf": " ",
                    "jd": "",
                    "kcxzmc": "任选",
                }
            ]
        }
    )

    assert grades == [
        CourseGrade(
            course_code="CODE",
            course_name="Course",
            score="90",
            course_type="任选",
        )
    ]
