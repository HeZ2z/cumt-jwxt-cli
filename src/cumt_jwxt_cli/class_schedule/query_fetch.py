"""Transport and parsing helpers for class timetable queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cumt_jwxt_cli.classrooms.query_fetch import CAMPUS_IDS
from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import (
    AppConfig,
    ClassScheduleEntry,
    ScheduleLesson,
    ScheduleSlot,
)
from cumt_jwxt_cli.schedule.parser import parse_week_ranges

CLASS_SCHEDULE_LIST_PATH = "/kbdy/bjkbdy_cxBjkbdyTjkbList.html"
CLASS_TIMETABLE_PATH = "/kbdy/bjkbdy_cxBjKb.html"

_PAGE_SIZE = 100
_MAX_PAGES = 5
# A class code/id has no CJK characters and is safe to send to the server-side
# bh_id filter, which avoids paging the entire term list for a code lookup.
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ClassScheduleFilters:
    """Validated user filters for one class timetable query."""

    campus: str = "all"
    grade: str | None = None
    college: str | None = None
    major: str | None = None
    class_query: str | None = None
    week: int | None = None
    list_only: bool = False


def build_list_data(config: AppConfig, filters: ClassScheduleFilters) -> dict[str, str]:
    """Build the JWXT form payload for the class timetable list."""

    data = {
        "xnm": config.query.year,
        "xqm": config.query.semester,
        "xqh_id": CAMPUS_IDS.get(filters.campus, ""),
        "njdm_id": filters.grade or "",
        "xb_id": "",
        "jg_id": filters.college or "",
        "zyh_id": filters.major or "",
        "zyfx_id": "",
        "bh_id": "",
        "xsdm": "",
        "pyccdm": "",
        "kclxdm": "",
        "kclbdm": "",
        "sfzhsjk": "",
        "kbsjlyqz": "",
        "zs": "",
        "yf": "",
        "sfcxxqh": "",
    }
    query = (filters.class_query or "").strip()
    if query and _CODE_PATTERN.match(query):
        data["bh_id"] = query
    return data


def query_class_schedule_list(
    config: AppConfig,
    client: object,
    filters: ClassScheduleFilters,
) -> tuple[ClassScheduleEntry, ...]:
    """Fetch and parse every class timetable entry matching the filters."""

    data = build_list_data(config, filters)
    raw_items = _fetch_list_items(client, data)
    return tuple(_parse_entry(item) for item in raw_items)


def _fetch_list_items(client: object, data: dict[str, str]) -> list[object]:
    items: list[object] = []
    previous_page: list[object] | None = None
    total: int | None = None

    for page_number in range(1, _MAX_PAGES + 1):
        page_data = {
            **data,
            "queryModel.showCount": str(_PAGE_SIZE),
            "queryModel.currentPage": str(page_number),
        }
        payload = _request_list_page(client, page_data)
        if total is None:
            total = _total_result(payload)
        page_items = _extract_list_items(payload)

        if not page_items:
            if total is not None and total > len(items):
                raise _ended_early_error(len(items), total)
            break
        # Some JWXT deployments ignore paging and repeat the same page.
        if previous_page is not None and page_items == previous_page:
            if total is not None and total > len(items):
                raise _ended_early_error(len(items), total)
            break

        items.extend(page_items)
        if total is not None and total <= len(items):
            break
        if len(page_items) < _PAGE_SIZE:
            if total is not None and total > len(items):
                previous_page = page_items
                continue
            break

        previous_page = page_items
    else:
        raise QueryError(
            f"JWXT class schedule list response exceeded {_MAX_PAGES} pages; "
            "refusing to return a truncated list."
        )

    return items


def _request_list_page(client: object, data: dict[str, str]) -> object:
    try:
        response = client.post(CLASS_SCHEDULE_LIST_PATH, data=data)
        _ensure_ok_response(response, "class schedule list")
        return response.json()
    except ValueError as exc:
        raise QueryError(
            "JWXT class schedule list response is not valid JSON."
        ) from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _extract_list_items(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise ParseError("Class schedule list payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError("Class schedule list payload must contain items.")
    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError("Class schedule list payload items must be a list.")
    return items


def _total_result(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalResult")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return None


def _ended_early_error(count: int, total: int) -> QueryError:
    return QueryError(
        f"JWXT class schedule list response ended early at {count} of {total} items."
    )


def match_class_schedules(
    entries: tuple[ClassScheduleEntry, ...],
    query: str | None,
) -> tuple[ClassScheduleEntry, ...]:
    """Match entries by exact code/name first, then by name substring."""

    if query is None:
        return entries
    text = query.strip()
    if not text:
        return entries

    exact = tuple(entry for entry in entries if _matches_exact(entry, text))
    if exact:
        return exact
    return tuple(entry for entry in entries if _matches_substring(entry, text))


def query_class_timetable(
    config: AppConfig,
    client: object,
    entry: ClassScheduleEntry,
) -> tuple[ScheduleLesson, ...]:
    """Fetch and parse the concrete timetable for one class schedule entry."""

    data = _build_timetable_data(config, entry)
    try:
        response = client.post(CLASS_TIMETABLE_PATH, data=data)
        _ensure_ok_response(response, "class timetable")
        payload = response.json()
    except ValueError as exc:
        raise QueryError("JWXT class timetable response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc
    return parse_class_timetable(payload)


def parse_class_timetable(payload: object) -> tuple[ScheduleLesson, ...]:
    """Parse a JWXT class timetable payload into schedule lessons."""

    if not isinstance(payload, dict):
        raise ParseError("Class timetable payload must be a JSON object.")
    if "kbList" not in payload:
        raise ParseError("Class timetable payload must contain kbList.")
    kb_list = payload["kbList"]
    if not isinstance(kb_list, list):
        raise ParseError("Class timetable payload kbList must be a list.")
    return tuple(_parse_lesson_item(item, index) for index, item in enumerate(kb_list))


def is_class_schedule_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)


def _build_timetable_data(
    config: AppConfig, entry: ClassScheduleEntry
) -> dict[str, str]:
    return {
        "xnm": config.query.year,
        "xqm": config.query.semester,
        "xnmc": "",
        "xqmmc": "",
        "xqh_id": entry.campus_id or "",
        "njdm_id": entry.grade_id or "",
        "zyh_id": entry.major_id or "",
        "bh_id": entry.class_id or "",
        "tjkbzdm": entry.schedule_code or "",
        "tjkbzxsdm": entry.schedule_aux or "",
        "zymc": entry.major_name or "",
        "jgmc": entry.college_name or "",
        "njmc": entry.grade_name or "",
        "bj": entry.class_name or "",
        "xkrs": entry.student_count or "",
        "bh": entry.class_code or "",
        "zs": "",
        "zxszjjs": "",
        "akcxqjchb": "",
        "xsdm": "",
        "kclxdm": "",
        "kclbdm": "",
        "kbsjlyqz": "",
        "yf": "",
        "kzlx": "ck",
        "sfcxxqh": "",
    }


def _ensure_ok_response(response: object, label: str) -> None:
    ensure_authenticated_response(response, label)
    # JWXT reports some application errors with its custom 911 status instead
    # of an HTTP error code, so it must be treated as a query failure.
    if getattr(response, "status_code", None) == 911:
        raise QueryError(f"JWXT {label} request failed with HTTP 911.")


def _matches_exact(entry: ClassScheduleEntry, text: str) -> bool:
    return text in {
        entry.class_id,
        entry.class_code,
        entry.class_name,
        entry.schedule_name,
    }


def _matches_substring(entry: ClassScheduleEntry, text: str) -> bool:
    return any(
        value is not None and text in value
        for value in (entry.class_name, entry.schedule_name)
    )


def _parse_entry(item: object) -> ClassScheduleEntry:
    if not isinstance(item, dict):
        raise ParseError("Class schedule list item must be a JSON object.")
    return ClassScheduleEntry(
        schedule_code=_text(item, "tjkbzdm"),
        schedule_aux=_text(item, "tjkbzxsdm"),
        schedule_name=_text(item, "tjkbmc"),
        class_id=_text(item, "bh_id"),
        class_code=_text(item, "bh"),
        class_name=_text(item, "bjmc"),
        major_name=_text(item, "zymc"),
        grade_name=_text(item, "njmc"),
        college_name=_text(item, "jgmc"),
        campus=_text(item, "xqmc"),
        student_count=_text(item, "xkrs"),
        campus_id=_text(item, "xqh_id"),
        grade_id=_text(item, "njdm_id"),
        major_id=_text(item, "zyh_id"),
    )


def _parse_lesson_item(item: object, index: int) -> ScheduleLesson:
    if not isinstance(item, dict):
        raise ParseError(f"Class timetable lesson item {index} must be an object.")

    course_code = _preferred_string(item, ("kch", "kch_id"), index)
    course_name = _required_string(item, "kcmc", index)
    weekday = _required_int(item, "xqj", index)
    if not 1 <= weekday <= 7:
        raise ParseError(
            f"Class timetable lesson item {index} field xqj must be between 1 and 7."
        )
    periods = _preferred_string(item, ("jcs", "jc"), index)
    weeks = parse_week_ranges(_required_string(item, "zcd", index))

    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class=_optional_string(item, "jxbmc"),
        teacher=_optional_string(item, "xm"),
        credits=_optional_string(item, "xf"),
        course_type=_optional_string(item, "kcxzjc")
        or _optional_string(item, "kclbmc"),
        slots=(
            ScheduleSlot(
                weekday=weekday,
                periods=periods,
                weeks=weeks,
                location=_optional_string(item, "cdmc"),
            ),
        ),
    )


def _preferred_string(
    item: dict[Any, Any], field_names: tuple[str, ...], index: int
) -> str:
    for field_name in field_names:
        value = _optional_string(item, field_name)
        if value is not None:
            return value
    joined = " or ".join(field_names)
    raise ParseError(
        f"Class timetable lesson item {index} missing required field: {joined}"
    )


def _required_string(item: dict[Any, Any], field_name: str, index: int) -> str:
    value = _optional_string(item, field_name)
    if value is None:
        raise ParseError(
            f"Class timetable lesson item {index} missing required field: {field_name}"
        )
    return value


def _optional_string(item: dict[Any, Any], field_name: str) -> str | None:
    value = item.get(field_name)
    if value is None:
        return None
    text = str(value).strip()
    if text in {"--", "None", "null"}:
        return None
    return text or None


def _required_int(item: dict[Any, Any], field_name: str, index: int) -> int:
    value = item.get(field_name)
    if isinstance(value, bool):
        raise ParseError(
            f"Class timetable lesson item {index} field {field_name} "
            "must be an integer."
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ParseError(
        f"Class timetable lesson item {index} field {field_name} must be an integer."
    )


def _text(item: dict[object, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if text in {"--", "None", "null"}:
        return None
    return text or None
