"""Transport helpers for exam schedule queries."""

from __future__ import annotations

import time

from cumt_jwxt_cli.client.paging import fetch_all_items
from cumt_jwxt_cli.errors import QueryError, SessionExpiredError
from cumt_jwxt_cli.exams.parser import parse_exam_list
from cumt_jwxt_cli.models import AppConfig, ExamInfo

EXAM_LIST_PATH = "/kwgl/kscx_cxXsksxxIndex.html"


def query_exam_list(config: AppConfig, client: object) -> list[ExamInfo]:
    """Fetch and parse the JWXT exam schedule."""

    items = fetch_all_items(
        client,
        EXAM_LIST_PATH,
        params={"doType": "query", "gnmkdm": "N358105"},
        data={
            "xnm": config.query.year,
            "xqm": config.query.semester,
            "_search": "false",
            "queryModel.sortName": "",
            "queryModel.sortOrder": "asc",
            "time": str(int(time.time() * 1000)),
        },
        label="exam list",
    )
    return parse_exam_list({"items": items})


def is_exam_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)
