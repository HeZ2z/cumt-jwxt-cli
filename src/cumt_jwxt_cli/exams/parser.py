"""Parse JWXT exam schedule payloads."""

from typing import Any

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.models import ExamInfo

_REQUIRED_FIELDS = {
    "kch": "course_code",
    "kcmc": "course_name",
}
_OPTIONAL_FIELDS = {
    "kssj": "exam_time",
    "cdmc": "location",
    "cdxqmc": "campus",
    "ksmc": "exam_name",
    "khfs": "exam_method",
    "sksj": "class_schedule",
    "jsxx": "teacher_info",
    "xf": "credit",
}


def parse_exam_list(payload: object) -> list[ExamInfo]:
    """Parse a JWXT exam list JSON object into exam records."""

    if not isinstance(payload, dict):
        raise ParseError("Exam list payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError("Exam list payload must contain items.")

    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError("Exam list payload items must be a list.")

    return [_parse_exam_item(item, index) for index, item in enumerate(items)]


def _parse_exam_item(item: object, index: int) -> ExamInfo:
    if not isinstance(item, dict):
        raise ParseError(f"Exam list item {index} must be a JSON object.")

    required_values = {
        target_name: _required_string(item, source_name, index)
        for source_name, target_name in _REQUIRED_FIELDS.items()
    }
    optional_values = {
        target_name: _optional_string(item, source_name, index)
        for source_name, target_name in _OPTIONAL_FIELDS.items()
    }

    return ExamInfo(**required_values, **optional_values)


def _required_string(item: dict[Any, Any], field_name: str, index: int) -> str:
    if field_name not in item:
        raise ParseError(f"Exam list item {index} missing required field: {field_name}")

    value = item[field_name]
    if not isinstance(value, str):
        raise ParseError(f"Exam list item {index} field {field_name} must be a string.")

    stripped = value.strip()
    if not stripped:
        raise ParseError(
            f"Exam list item {index} field {field_name} must not be blank."
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
        raise ParseError(f"Exam list item {index} field {field_name} must be a string.")

    stripped = value.strip()
    return stripped or None
