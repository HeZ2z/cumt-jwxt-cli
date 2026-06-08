"""Transport helpers for exam schedule queries."""

from __future__ import annotations

import time

from cumt_jwxt_cli.errors import QueryError
from cumt_jwxt_cli.exams.parser import parse_exam_list
from cumt_jwxt_cli.models import AppConfig, ExamInfo

EXAM_LIST_PATH = "/kwgl/kscx_cxXsksxxIndex.html"


def query_exam_list(config: AppConfig, client: object) -> list[ExamInfo]:
    """Fetch and parse the JWXT exam schedule."""

    try:
        response = client.post(
            EXAM_LIST_PATH,
            params={"doType": "query", "gnmkdm": "N358105"},
            data={
                "xnm": config.query.year,
                "xqm": config.query.semester,
                "_search": "false",
                "queryModel.showCount": "100",
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
        )
        content_type = ""
        headers = getattr(response, "headers", None)
        if hasattr(headers, "get"):
            content_type = str(headers.get("content-type", "")).lower()
        status_code = getattr(response, "status_code", None)
        # JWXT returns HTTP 901 when the login session has expired.
        if status_code == 901:
            raise QueryError("JWXT exam list request failed with HTTP 901.")
        if "text/html" in content_type:
            raise QueryError("JWXT exam list response looks like an HTML login page.")
        return parse_exam_list(response.json())
    except ValueError as exc:
        raise QueryError("JWXT exam list response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def is_exam_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    message = str(exc).lower()
    session_markers = (
        "http 901",
        "html login page",
    )
    return any(marker in message for marker in session_markers)
