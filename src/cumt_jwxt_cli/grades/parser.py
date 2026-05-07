"""Parse JWXT grade list payloads."""

from typing import Any

from bs4 import BeautifulSoup

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.models import CourseGrade, GradeDetail, GradeDetailComponent

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


def parse_grade_detail(
    html_content: str,
    *,
    course_code: str,
    fallback_course_name: str,
) -> GradeDetail:
    """Parse a JWXT course grade detail HTML page."""

    soup = BeautifulSoup(html_content, "html.parser")
    course_name = _extract_detail_course_name(soup) or fallback_course_name
    table = soup.find("table", id="subtab")
    if table is None:
        raise ParseError("Grade detail page must contain table#subtab.")

    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody is not None else table.find_all("tr")
    components: list[GradeDetailComponent] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        name = _clean_detail_component_name(cells[0].get_text(" ", strip=True))
        percentage = cells[1].get_text(" ", strip=True)
        score = cells[2].get_text(" ", strip=True)
        if name or percentage or score:
            components.append(
                GradeDetailComponent(
                    name=name,
                    percentage=percentage,
                    score=score,
                )
            )

    if not components:
        raise ParseError("Grade detail page must contain score components.")

    return GradeDetail(
        course_code=course_code,
        course_name=course_name,
        components=tuple(components),
    )


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


def _extract_detail_course_name(soup: BeautifulSoup) -> str | None:
    course_name_span = soup.find("span", class_="red2")
    if course_name_span is None:
        return None
    course_name = course_name_span.get_text(" ", strip=True)
    return course_name or None


def _clean_detail_component_name(value: str) -> str:
    return value.strip().removeprefix("【").removesuffix("】").strip()
