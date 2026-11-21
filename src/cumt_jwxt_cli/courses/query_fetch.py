"""Transport and parsing helpers for course teaching-session queries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import AppConfig, CourseSession

PAGE_PATH = "/design/viewFunc_cxDesignFuncPageIndex.html"
PAGE_PARAMS = {"gnmkdm": "N219904", "layout": "default"}
LIST_PATH = "/design/funcData_cxFuncDataList.html"

# ``limit`` 0 means "all", but unbounded paging against JWXT is unsafe.
MAX_RESULTS = 1000
_DEFAULT_PAGE_SIZE = 200
_MAX_PAGES = 5

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_GUID_ATTRIBUTE = "data-func_widget_guid"
_GUID_FALLBACK_PATTERN = re.compile(
    r"func_widget_guid\s*[=:]\s*['\"]([0-9A-Fa-f]+)['\"]"
)


@dataclass(frozen=True)
class CourseQueryOptions:
    """Validated user options for one course teaching-session query."""

    course: str | None = None
    teacher: str | None = None
    room: str | None = None
    weekday: int | None = None
    periods: str | None = None
    weeks: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class CourseQueryResult:
    """Fetched course sessions and the server-side total before display limiting."""

    sessions: tuple[CourseSession, ...]
    total: int
    year: str = ""
    semester: str = ""


def parse_widget_guid(page_html: object) -> str:
    """Extract the ``func_widget_guid`` from the course query page.

    The guid is deployment-specific, so it must be read from the page rather
    than hard-coded. A regex fallback covers attribute placement changes.
    """

    if not isinstance(page_html, str) or not page_html.strip():
        raise ParseError("Course query page is empty.")

    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup.find_all(attrs={_GUID_ATTRIBUTE: True}):
        value = str(tag.get(_GUID_ATTRIBUTE, "")).strip()
        if value:
            return value

    match = _GUID_FALLBACK_PATTERN.search(page_html)
    if match is not None:
        return match.group(1)

    raise ParseError("Course query page is missing func_widget_guid.")


def build_query_data(config: AppConfig, options: CourseQueryOptions) -> dict[str, str]:
    """Build the JWXT form payload for one course teaching-session query."""

    data = {
        "xnm": config.query.year,
        "xqm": config.query.semester,
    }
    if options.course:
        data["kch_id"] = options.course
    if options.teacher:
        data["js"] = options.teacher
    if options.room:
        data["jxcd"] = options.room
    if options.weekday is not None:
        data["xqj"] = str(options.weekday)
    if options.periods:
        # The JWXT field expects a bare range such as "1-2"; the "节" suffix is
        # rejected by the server.
        data["skjc"] = options.periods
    if options.weeks:
        data["qsjsz"] = options.weeks
    return data


def query_course_sessions(
    config: AppConfig,
    client: object,
    options: CourseQueryOptions,
) -> CourseQueryResult:
    """Fetch the widget guid, then page through matching course sessions."""

    page_html = _fetch_page(client)
    guid = parse_widget_guid(page_html)

    data = build_query_data(config, options)
    page_size = _page_size(options.limit)
    if options.limit > 0:
        # Fetch only as many pages as the display limit can use.
        max_pages = min(_MAX_PAGES, (options.limit + page_size - 1) // page_size)
    else:
        max_pages = _MAX_PAGES
    raw_items, total = _fetch_items(
        client,
        guid,
        data,
        page_size=page_size,
        max_pages=max_pages,
    )
    sessions = tuple(_parse_item(item) for item in raw_items)
    return CourseQueryResult(
        sessions=sessions,
        total=total if total is not None else len(sessions),
        year=config.query.year,
        semester=config.query.semester,
    )


def is_course_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)


def _page_size(limit: int) -> int:
    if limit <= 0:
        return _DEFAULT_PAGE_SIZE
    return min(limit, _DEFAULT_PAGE_SIZE)


def _fetch_page(client: object) -> str:
    try:
        response = client.get(PAGE_PATH, params=dict(PAGE_PARAMS))
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc

    status_code = getattr(response, "status_code", None)
    # This page is server-rendered HTML, so text/html is expected; only
    # redirects and HTTP 901 indicate an expired session here.
    if status_code == 901 or status_code in _REDIRECT_STATUSES:
        raise SessionExpiredError(
            f"JWXT course query page request failed with HTTP {status_code}."
        )

    page_html = getattr(response, "text", None)
    if not isinstance(page_html, str) or not page_html.strip():
        raise QueryError("JWXT course query page response is empty.")
    return page_html


def _fetch_items(
    client: object,
    guid: str,
    data: dict[str, str],
    *,
    page_size: int,
    max_pages: int,
) -> tuple[list[object], int | None]:
    items: list[object] = []
    previous_page: list[object] | None = None
    total: int | None = None

    for page_number in range(1, max_pages + 1):
        page_data = {
            **data,
            "queryModel.showCount": str(page_size),
            "queryModel.currentPage": str(page_number),
        }
        # GET with the same parameters returns 200 with empty items, so the
        # list must be fetched with POST.
        payload = _request_json(client, guid, page_data)
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
    guid: str,
    data: dict[str, str],
) -> object:
    try:
        response = client.post(LIST_PATH, params={"func_widget_guid": guid}, data=data)
        ensure_authenticated_response(response, "course list")
        return response.json()
    except ValueError as exc:
        raise QueryError("JWXT course list response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _extract_items(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise ParseError("Course payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError("Course payload must contain items.")
    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError("Course payload items must be a list.")
    return items


def _total_result(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalResult")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return None


def _parse_item(item: object) -> CourseSession:
    if not isinstance(item, dict):
        raise ParseError("Course item must be a JSON object.")
    return CourseSession(
        course_code=_text(item, "kch"),
        course_name=_text(item, "kcmc"),
        credits=_text(item, "xf"),
        total_hours=_text(item, "rwzxs"),
        weekly_hours=_text(item, "zhxs"),
        course_nature=_text(item, "kcxzmc"),
        teacher_name=_text(item, "xm"),
        teaching_class=_text(item, "jxbmc"),
        class_composition=_text(item, "jxbzc"),
        class_size=_text(item, "jxbrs"),
        enrolled_count=_text(item, "xkrs"),
        college=_text(item, "kkxy"),
        campus=_text(item, "xqmc"),
        building=_text(item, "jxlmc"),
        room=_text(item, "cdmc"),
        weekday=_text(item, "xqj"),
        periods=_text(item, "skjc"),
        start_week=_text(item, "qsjsz"),
        schedule_text=_text(item, "sksj"),
        location_text=_text(item, "jxdd"),
    )


def _text(item: dict[object, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if text in {"--", "None", "null"}:
        return None
    return text or None
