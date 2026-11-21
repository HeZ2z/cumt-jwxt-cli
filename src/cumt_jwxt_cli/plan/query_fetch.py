"""Transport and parsing helpers for teaching execution plan queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import AppConfig, TeachingPlanCourse, TeachingPlanHeader

PLAN_HEADER_PATH = "/jxzxjhgl/jxzxjhck_cxJxzxjhckIndex.html"
PLAN_COURSE_PATH = "/jxzxjhgl/jxzxjhkcxx_cxJxzxjhkcxxIndex.html"
# The course endpoint requires gnmkdm; without it JWXT returns an HTML
# "no permission" page instead of JSON.
COURSE_GNMKDM = "N153540"

_PAGE_SIZE = 200
_MAX_PAGES = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_COURSE_SORT = "jyxdxnm,jyxdxqm,kch"


@dataclass(frozen=True)
class PlanFilters:
    """Validated user filters for one teaching plan query."""

    grade: str | None = None
    college: str | None = None
    major: str | None = None
    plan_id: str | None = None
    list_only: bool = False
    course: str | None = None
    study_year: str | None = None
    # Already mapped from the CLI's 1/2/3 to JWXT's 3/12/16.
    study_term: str | None = None
    study_type: str | None = None

    @property
    def has_header_filter(self) -> bool:
        return any((self.grade, self.college, self.major))


def build_plan_data(filters: PlanFilters) -> dict[str, str]:
    """Build the JWXT parameters for the teaching plan header list.

    Empty filters are allowed by the server but return the entire plan table,
    so callers must validate that at least one narrowing filter is present.
    """

    return {
        "doType": "query",
        "jg_id": filters.college or "",
        "njdm_id": filters.grade or "",
        "dlbs": "",
        "zyh_id": filters.major or "",
        "currentPage_cx": "1",
        "queryModel.showCount": str(_PAGE_SIZE),
        "queryModel.currentPage": "1",
        "queryModel.sortName": "",
        "queryModel.sortOrder": "asc",
    }


def build_course_data(filters: PlanFilters) -> dict[str, str]:
    """Build the JWXT parameters for a plan's course list.

    All eight filter keys must be present even when empty, otherwise the
    server silently returns zero rows.
    """

    return {
        "doType": "query",
        "gnmkdm": COURSE_GNMKDM,
        "jyxdxnm": filters.study_year or "",
        "jyxdxqm": filters.study_term or "",
        "yxxdxnm": "",
        "yxxdxqm": "",
        "shzt": "",
        "kch": "",
        "jxzxjhxx_id": filters.plan_id or "",
        "xdlx": filters.study_type or "",
        "queryModel.showCount": str(_PAGE_SIZE),
        "queryModel.currentPage": "1",
        "queryModel.sortName": _COURSE_SORT,
        "queryModel.sortOrder": "asc",
    }


def query_plan_headers(
    config: AppConfig,
    client: object,
    filters: PlanFilters,
) -> tuple[TeachingPlanHeader, ...]:
    """Fetch every teaching plan header matching the filters."""

    raw_items, _total = _fetch_items(
        client,
        PLAN_HEADER_PATH,
        build_plan_data(filters),
        label="teaching plan list",
    )
    return tuple(parse_plan_header(item) for item in raw_items)


def query_plan_courses(
    config: AppConfig,
    client: object,
    filters: PlanFilters,
    plan_id: str,
) -> tuple[TeachingPlanCourse, ...]:
    """Fetch every course row of one teaching plan."""

    course_filters = PlanFilters(
        grade=filters.grade,
        college=filters.college,
        major=filters.major,
        plan_id=plan_id,
        list_only=filters.list_only,
        course=filters.course,
        study_year=filters.study_year,
        study_term=filters.study_term,
        study_type=filters.study_type,
    )
    raw_items, _total = _fetch_items(
        client,
        PLAN_COURSE_PATH,
        build_course_data(course_filters),
        label="teaching plan course list",
    )
    return tuple(parse_plan_course(item) for item in raw_items)


def parse_plan_header(item: object) -> TeachingPlanHeader:
    """Parse one plan header item into a typed model."""

    if not isinstance(item, dict):
        raise ParseError("Teaching plan header item must be a JSON object.")
    plan_id = _text(item, "jxzxjhxx_id")
    if plan_id is None:
        raise ParseError("Teaching plan header item is missing jxzxjhxx_id.")
    return TeachingPlanHeader(
        plan_id=plan_id,
        grade=_text(item, "njdm") or _text(item, "njmc"),
        major_code=_text(item, "zyh"),
        major_name=_text(item, "zymc"),
        college_id=_text(item, "jg_id"),
        campus=_text(item, "xqmc"),
        program_length=_text(item, "xz"),
        course_count=_text(item, "kcs"),
        total_credits=_text(item, "zdxf"),
    )


def parse_plan_course(item: object) -> TeachingPlanCourse:
    """Parse one plan course item into a typed model."""

    if not isinstance(item, dict):
        raise ParseError("Teaching plan course item must be a JSON object.")
    course_code = _text(item, "kch") or _text(item, "kch_id")
    course_name = _text(item, "kcmc")
    if course_code is None and course_name is None:
        raise ParseError("Teaching plan course item is missing both kch and kcmc.")
    return TeachingPlanCourse(
        course_code=course_code,
        course_name=course_name,
        course_name_en=_text(item, "kcywmc"),
        credits=_text(item, "xf"),
        total_hours=_text(item, "zxs"),
        study_year=_text(item, "jyxdxnm"),
        study_term=_text(item, "jyxdxqm"),
        allowed_terms=_text(item, "yyxdxnxqmc"),
        category_name=_text(item, "kcxzmc"),
        class_category=_text(item, "kclbmc"),
        assessment_method=_text(item, "khfsdm"),
        exam_method=_text(item, "ksfsdm"),
        department=_text(item, "kkbmmc"),
        week_range=_text(item, "qsjsz"),
        study_type=_text(item, "xdlx"),
        status=_text(item, "shzt"),
    )


def is_plan_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)


def _fetch_items(
    client: object,
    path: str,
    data: dict[str, str],
    *,
    label: str,
) -> tuple[list[object], int | None]:
    items: list[object] = []
    previous_page: list[object] | None = None
    total: int | None = None

    for page_number in range(1, _MAX_PAGES + 1):
        page_data = {
            **data,
            "queryModel.showCount": str(_PAGE_SIZE),
            "queryModel.currentPage": str(page_number),
        }
        if "currentPage_cx" in page_data:
            page_data["currentPage_cx"] = str(page_number)
        payload = _request_json(client, path, page_data, label)
        if total is None:
            total = _total_result(payload)
        page_items = _extract_items(payload, label)

        if not page_items:
            if total is not None and total > len(items):
                raise _ended_early_error(label, len(items), total)
            break
        # Some JWXT deployments ignore paging and repeat the same page.
        if previous_page is not None and page_items == previous_page:
            if total is not None and total > len(items):
                raise _ended_early_error(label, len(items), total)
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
            f"JWXT {label} response exceeded {_MAX_PAGES} pages; "
            "refusing to return a truncated list."
        )

    return items, total


def _request_json(
    client: object,
    path: str,
    data: dict[str, str],
    label: str,
) -> object:
    try:
        response = client.get(path, params=data)
        _ensure_ok(response, label)
        return response.json()
    except ValueError as exc:
        raise QueryError(f"JWXT {label} response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _ensure_ok(response: object, label: str) -> None:
    ensure_authenticated_response(response, label)
    # JWXT reports some application errors with its custom 911 status instead
    # of an HTTP error code, so it must be treated as a query failure.
    if getattr(response, "status_code", None) == 911:
        raise QueryError(f"JWXT {label} request failed with HTTP 911.")


def _extract_items(payload: object, label: str) -> list[object]:
    if not isinstance(payload, dict):
        raise ParseError(f"Teaching plan {label} payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError(f"Teaching plan {label} payload must contain items.")
    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError(f"Teaching plan {label} payload items must be a list.")
    return items


def _total_result(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalResult")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return None


def _ended_early_error(label: str, count: int, total: int) -> QueryError:
    return QueryError(f"JWXT {label} response ended early at {count} of {total} items.")


def _text(item: dict[Any, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if text in {"--", "None", "null"}:
        return None
    return text or None
