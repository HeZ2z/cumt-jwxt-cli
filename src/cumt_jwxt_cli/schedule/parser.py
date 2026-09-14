"""Parse JWXT personal schedule payloads."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from cumt_jwxt_cli.errors import ParseError
from cumt_jwxt_cli.models import (
    PeriodTime,
    ScheduleLesson,
    ScheduleListData,
    ScheduleSlot,
    ScheduleUnscheduledCourse,
)

_WEEK_PART_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?周(?:\((单|双)\))?$")
# JWXT separates the two dates with an ASCII tilde in some semesters and the
# Chinese character 至 (U+81F3) in others, so match the dates themselves.
_WEEK_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_week_ranges(value: str) -> tuple[int, ...]:
    """Expand a zcd week string into a sorted, deduplicated week tuple.

    Supports comma-separated ranges such as ``1-5周`` and ``7-10周``, single
    weeks such as ``12周``, and the ``(单)``/``(双)`` parity suffix.
    """

    if not isinstance(value, str) or not value.strip():
        raise ParseError("Schedule week string must be a non-blank string.")

    weeks: set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        match = _WEEK_PART_PATTERN.match(part)
        if match is None:
            raise ParseError(f"Unsupported schedule week segment: {part}")
        start = int(match[1])
        end = int(match[2]) if match[2] is not None else start
        if end < start:
            raise ParseError(f"Schedule week range is reversed: {part}")
        parity = match[3]
        for week in range(start, end + 1):
            if parity == "单" and week % 2 == 0:
                continue
            if parity == "双" and week % 2 == 1:
                continue
            weeks.add(week)

    if not weeks:
        raise ParseError(f"Schedule week string has no weeks: {value}")
    return tuple(sorted(weeks))


def parse_schedule_payload(payload: object) -> ScheduleListData:
    """Parse a JWXT personal schedule JSON object."""

    if not isinstance(payload, dict):
        raise ParseError("Schedule payload must be a JSON object.")
    if "kbList" not in payload:
        raise ParseError("Schedule payload must contain kbList.")

    kb_list = payload["kbList"]
    if not isinstance(kb_list, list):
        raise ParseError("Schedule payload kbList must be a list.")

    sjk_list = payload.get("sjkList", [])
    if not isinstance(sjk_list, list):
        raise ParseError("Schedule payload sjkList must be a list.")

    return ScheduleListData(
        lessons=tuple(
            _parse_lesson_item(item, index) for index, item in enumerate(kb_list)
        ),
        unscheduled=tuple(
            _parse_unscheduled_item(item, index) for index, item in enumerate(sjk_list)
        ),
    )


def parse_period_times(payload: object) -> tuple[PeriodTime, ...]:
    """Parse a JWXT period time JSON list."""

    if not isinstance(payload, list):
        raise ParseError("Schedule period time payload must be a JSON list.")
    return tuple(
        _parse_period_time_item(item, index) for index, item in enumerate(payload)
    )


def parse_week_dates(payload: object) -> dict[int, date]:
    """Parse a JWXT week calendar list into a week-number to Monday mapping."""

    if not isinstance(payload, list):
        raise ParseError("Schedule week date payload must be a JSON list.")

    week_dates: dict[int, date] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ParseError(f"Schedule week date item {index} must be an object.")
        week = _required_int(item, "zs", index, "week date")
        raw_range = item.get("zcrq")
        if not isinstance(raw_range, str):
            continue
        match = _WEEK_DATE_PATTERN.search(raw_range)
        if match is None:
            continue
        week_dates[week] = date.fromisoformat(match.group(0))
    return week_dates


def _parse_lesson_item(item: object, index: int) -> ScheduleLesson:
    if not isinstance(item, dict):
        raise ParseError(f"Schedule lesson item {index} must be a JSON object.")

    course_code = _preferred_string(item, ("kch_id", "kch"), index)
    course_name = _required_string(item, "kcmc", index)
    weekday = _required_int(item, "xqj", index, "lesson")
    if not 1 <= weekday <= 7:
        raise ParseError(
            f"Schedule lesson item {index} field xqj must be between 1 and 7."
        )
    periods = _preferred_string(item, ("jcs", "jc"), index)
    weeks = parse_week_ranges(_required_string(item, "zcd", index))

    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=_optional_string(item, "jxbmc"),
        teacher=_optional_string(item, "xm"),
        credits=_optional_string(item, "xf"),
        course_type=_optional_string(item, "kclbmc"),
        slots=(
            ScheduleSlot(
                weekday=weekday,
                periods=periods,
                weeks=weeks,
                location=_optional_string(item, "cdmc"),
            ),
        ),
    )


def _parse_unscheduled_item(item: object, index: int) -> ScheduleUnscheduledCourse:
    if not isinstance(item, dict):
        raise ParseError(f"Schedule unscheduled item {index} must be a JSON object.")

    return ScheduleUnscheduledCourse(
        course_name=_required_string(item, "kcmc", index),
        teacher=_optional_string(item, "jsxm"),
        week_range=_optional_string(item, "qsjsz"),
        credits=_optional_string(item, "xf"),
    )


def _parse_period_time_item(item: object, index: int) -> PeriodTime:
    if not isinstance(item, dict):
        raise ParseError(f"Schedule period time item {index} must be a JSON object.")

    return PeriodTime(
        period=_required_string(item, "jcmc", index),
        start=_required_string(item, "qssj", index),
        end=_required_string(item, "jssj", index),
        section=_optional_string(item, "rsdmc"),
    )


def _preferred_string(
    item: dict[Any, Any], field_names: tuple[str, ...], index: int
) -> str:
    for field_name in field_names:
        value = _optional_string(item, field_name)
        if value is not None:
            return value
    joined = " or ".join(field_names)
    raise ParseError(f"Schedule lesson item {index} missing required field: {joined}")


def _required_string(item: dict[Any, Any], field_name: str, index: int) -> str:
    if field_name not in item:
        raise ParseError(f"Schedule item {index} missing required field: {field_name}")
    value = item[field_name]
    if not isinstance(value, str):
        raise ParseError(f"Schedule item {index} field {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ParseError(f"Schedule item {index} field {field_name} must not be blank.")
    return stripped


def _optional_string(item: dict[Any, Any], field_name: str) -> str | None:
    if field_name not in item:
        return None
    value = item[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ParseError(f"Schedule field {field_name} must be a string.")
    stripped = value.strip()
    return stripped or None


def _required_int(
    item: dict[Any, Any],
    field_name: str,
    index: int,
    label: str,
) -> int:
    if field_name not in item:
        raise ParseError(
            f"Schedule {label} item {index} missing required field: {field_name}"
        )
    value = item[field_name]
    # JWXT encodes some integer fields (xqj, zs) as numeric strings.
    if isinstance(value, bool):
        raise ParseError(
            f"Schedule {label} item {index} field {field_name} must be an integer."
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    raise ParseError(
        f"Schedule {label} item {index} field {field_name} must be an integer."
    )
