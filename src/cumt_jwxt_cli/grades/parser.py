"""Parse JWXT grade list payloads."""

from typing import Any

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.models import CourseGrade

_REQUIRED_FIELDS = {
    "kch": "course_code",
    "kcmc": "course_name",
    "cj": "score",
}
_OPTIONAL_FIELDS = {
    "xf": "credit",
    "jd": "grade_point",
    "kcxzmc": "course_type",
    "khfsmc": "exam_type",
    "jxb_id": "teaching_class_id",
}


def parse_grade_list(payload: object) -> list[CourseGrade]:
    """Parse a JWXT grade list JSON object into course grade records."""

    if not isinstance(payload, dict):
        raise ParseError("Grade list payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError("Grade list payload must contain items.")

    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError("Grade list payload items must be a list.")

    return [_parse_grade_item(item, index) for index, item in enumerate(items)]


def _parse_grade_item(item: object, index: int) -> CourseGrade:
    if not isinstance(item, dict):
        raise ParseError(f"Grade list item {index} must be a JSON object.")

    required_values = {
        target_name: _required_string(item, source_name, index)
        for source_name, target_name in _REQUIRED_FIELDS.items()
    }
    optional_values = {
        target_name: _optional_string(item, source_name, index)
        for source_name, target_name in _OPTIONAL_FIELDS.items()
    }

    return CourseGrade(**required_values, **optional_values)


def _required_string(item: dict[Any, Any], field_name: str, index: int) -> str:
    if field_name not in item:
        raise ParseError(
            f"Grade list item {index} missing required field: {field_name}"
        )

    value = item[field_name]
    if not isinstance(value, str):
        raise ParseError(
            f"Grade list item {index} field {field_name} must be a string."
        )

    stripped = value.strip()
    if not stripped:
        raise ParseError(
            f"Grade list item {index} field {field_name} must not be blank."
        )
    return stripped


def _optional_string(
    item: dict[Any, Any],
    field_name: str,
    index: int,
) -> str | None:
    if field_name not in item:
        return None

    value = item[field_name]
    if not isinstance(value, str):
        raise ParseError(
            f"Grade list item {index} field {field_name} must be a string."
        )

    stripped = value.strip()
    return stripped or None
