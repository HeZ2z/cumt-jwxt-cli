"""Transport helpers for free classroom queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import AppConfig, FreeClassroom

CLASSROOM_LIST_PATH = "/cdjy/cdjy_cxKxcdlb.html"
CLASSROOM_LIST_PARAMS = {"doType": "query", "gnmkdm": "N2155"}

CAMPUS_IDS = {"all": "", "nanhu": "2", "wenchang": "1"}

MAX_RESULTS = 5000
_MAX_PAGES = 10
_DEFAULT_PAGE_SIZE = 500

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK_PATTERN = re.compile(r"^\d{2}:\d{2}$")

_AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": (
        "http://jwxt.cumt.edu.cn/jwglxt/cdjy/"
        "cdjy_cxKxcdlb.html?gnmkdm=N2155&layout=default"
    ),
}


@dataclass(frozen=True)
class ClassroomQueryOptions:
    """Validated user options for one free classroom query."""

    date: str
    start: str | None = None
    end: str | None = None
    campus: str = "all"
    building: str = ""
    min_seats: int | None = None
    max_seats: int | None = None
    lendable: bool = False
    limit: int = 50


@dataclass(frozen=True)
class ClassroomQueryResult:
    """Fetched classrooms and the server-side total before display limiting."""

    classrooms: tuple[FreeClassroom, ...]
    total: int
    year: str = ""
    semester: str = ""


def parse_date(value: str) -> str:
    """Validate a ``YYYY-MM-DD`` query date and return it unchanged."""

    if not _DATE_PATTERN.match(value):
        raise ValueError(f"日期必须为 YYYY-MM-DD 格式: {value}")
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"无效日期: {value}") from exc
    return value


def parse_clock(value: str) -> str:
    """Validate an ``HH:MM`` clock time and return it unchanged."""

    if not _CLOCK_PATTERN.match(value):
        raise ValueError(f"时刻必须为 HH:MM 格式: {value}")
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"无效时刻: {value}") from exc
    return value


def build_query_data(
    config: AppConfig, options: ClassroomQueryOptions
) -> dict[str, str]:
    """Build the JWXT form payload for one free classroom query."""

    data = {
        "xnm": config.query.year,
        "xqm": config.query.semester,
        "xqh_id": CAMPUS_IDS.get(options.campus, ""),
        "cdlb_id": "",
        "cdejlb_id": "",
        "qszws": "" if options.min_seats is None else str(options.min_seats),
        "jszws": "" if options.max_seats is None else str(options.max_seats),
        "cdmc": "",
        "lh": options.building,
        "jyfs": "1",
        "cdjylx": "",
        "qssj": options.date,
        "jssj": options.date,
        "qssd": options.start or "",
        "jssd": options.end or "",
        "_search": "false",
        "queryModel.sortName": "",
        "queryModel.sortOrder": "asc",
    }
    if options.lendable:
        data["sfkjy"] = "1"
    return data


def query_classrooms(
    config: AppConfig,
    client: object,
    options: ClassroomQueryOptions,
) -> ClassroomQueryResult:
    """Fetch and parse free classrooms for one date/time window."""

    data = build_query_data(config, options)
    # Fetch the full result set before display limiting so client-side sorting
    # still sees every page; the safety cap bounds pathological responses.
    raw_items, total = _fetch_items(client, data, page_size=_DEFAULT_PAGE_SIZE)
    classrooms = tuple(_parse_item(item) for item in raw_items)
    return ClassroomQueryResult(
        classrooms=classrooms,
        total=total if total is not None else len(classrooms),
        year=config.query.year,
        semester=config.query.semester,
    )


def is_classroom_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)


def _fetch_items(
    client: object,
    data: dict[str, str],
    *,
    page_size: int,
) -> tuple[list[object], int | None]:
    items: list[object] = []
    previous_page: list[object] | None = None
    total: int | None = None

    for page_number in range(1, _MAX_PAGES + 1):
        page_data = {
            **data,
            "queryModel.showCount": str(page_size),
            "queryModel.currentPage": str(page_number),
        }
        payload = _request_json(
            client,
            CLASSROOM_LIST_PATH,
            CLASSROOM_LIST_PARAMS,
            page_data,
            "classroom list",
        )
        if total is None:
            total = _total_result(payload)
        page_items = _extract_items(payload)

        if not page_items:
            break
        # Some JWXT deployments ignore paging and repeat the same page.
        if previous_page is not None and page_items == previous_page:
            break

        items.extend(page_items)
        if len(items) >= MAX_RESULTS:
            del items[MAX_RESULTS:]
            break
        if total is not None and len(items) >= total:
            break
        if len(page_items) < page_size:
            break

        previous_page = page_items

    return items, total


def _request_json(
    client: object,
    path: str,
    params: dict[str, str],
    data: dict[str, str],
    label: str,
) -> object:
    try:
        response = client.post(
            path, params=params, data=data, headers=dict(_AJAX_HEADERS)
        )
        ensure_authenticated_response(response, label)
        return response.json()
    except ValueError as exc:
        raise QueryError(f"JWXT {label} response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _extract_items(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise ParseError("Classroom payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError("Classroom payload must contain items.")
    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError("Classroom payload items must be a list.")
    return items


def _total_result(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalResult")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return None


def _parse_item(item: object) -> FreeClassroom:
    if not isinstance(item, dict):
        raise ParseError("Classroom item must be a JSON object.")
    return FreeClassroom(
        room_name=_text(item, "cdmc"),
        room_code=_text(item, "cdbh"),
        building=_text(item, "jxlmc"),
        floor=_text(item, "lch"),
        campus=_text(item, "xqmc"),
        category=_text(item, "cdlbmc"),
        seats=_text(item, "zws") or _text(item, "sjzws"),
        exam_seats=_text(item, "kszws1"),
        lendable=_yes_no(_text(item, "sfkjy")),
        schedulable=_yes_no(_text(item, "sfkpk")),
    )


def _text(item: dict[object, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yes_no(value: str | None) -> bool | None:
    if value == "是":
        return True
    if value == "否":
        return False
    return None
