"""Transport and parsing helpers for grade queries."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from cumt_jwxt_cli.errors import ParseError, QueryError
from cumt_jwxt_cli.grades.parser import parse_grade_detail, parse_grade_list
from cumt_jwxt_cli.models import AppConfig, CourseGrade, GradeDetail, GradeQueryResult

GRADE_LIST_PATH = "/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"
GRADE_DETAIL_PATH = "/cjcx/cjcx_cxCjxqGjh.html"
_LOGGER = logging.getLogger(__name__)


def query_grade_list(config: AppConfig, client: object) -> list[CourseGrade]:
    """Fetch and parse the JWXT grade list response."""

    try:
        response = client.post(
            GRADE_LIST_PATH,
            data={
                "xnm": config.query.year,
                "xqm": config.query.semester,
                "sfzgcj": "",
                "kcbj": "",
                "_search": "false",
                "queryModel.showCount": "100",
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": "13",
            },
        )
        content_type = ""
        headers = getattr(response, "headers", None)
        if hasattr(headers, "get"):
            content_type = str(headers.get("content-type", "")).lower()
        status_code = getattr(response, "status_code", None)
        if status_code == 901:
            raise QueryError("JWXT grade list request failed with HTTP 901.")
        if "text/html" in content_type:
            raise QueryError("JWXT grade list response looks like an HTML login page.")
        return parse_grade_list(response.json())
    except ValueError as exc:
        raise QueryError("JWXT grade list response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def query_grade_details_if_needed(
    config: AppConfig,
    client: object,
    result: GradeQueryResult,
    *,
    force: bool,
    executor_factory: Callable[..., object] = ThreadPoolExecutor,
) -> tuple[GradeDetail, ...]:
    if not config.grades.include_details_on_change:
        return ()
    if not result.changes and not force:
        return ()

    grades = tuple(
        grade
        for grade in grades_for_detail_query(result, force=force)
        if grade.teaching_class_id is not None
    )
    if not grades:
        return ()

    max_workers = max(1, min(config.grades.detail_concurrency, len(grades)))
    with executor_factory(max_workers=max_workers) as executor:
        details = executor.map(
            lambda grade: query_grade_detail(config, client, grade),
            grades,
        )
    return tuple(detail for detail in details if detail is not None)


def grades_for_detail_query(
    result: GradeQueryResult,
    *,
    force: bool,
) -> tuple[CourseGrade, ...]:
    if force:
        return result.grades
    changed_keys = {
        change.after.course_code
        for change in result.changes
        if change.after is not None
    }
    return tuple(grade for grade in result.grades if grade.course_code in changed_keys)


def query_grade_detail(
    config: AppConfig,
    client: object,
    grade: CourseGrade,
) -> GradeDetail | None:
    try:
        response = client.post(
            GRADE_DETAIL_PATH,
            params={
                "time": str(int(time.time() * 1000)),
                "gnmkdm": "N305005",
            },
            data={
                "jxb_id": grade.teaching_class_id or "",
                "xnm": config.query.year,
                "xqm": config.query.semester,
                "kcmc": grade.course_name,
            },
        )
        return parse_grade_detail(
            response.text,
            course_code=grade.course_code,
            fallback_course_name=grade.course_name,
        )
    except (AttributeError, ParseError, QueryError) as exc:
        _LOGGER.warning(
            "Skipping grade detail for course %s after detail query or parse failure.",
            grade.course_code,
            exc_info=exc,
        )
        return None


def is_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    message = str(exc).lower()
    session_markers = (
        "http 901",
        "html login page",
    )
    return any(marker in message for marker in session_markers)
