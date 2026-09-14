"""Transport helpers for personal schedule queries."""

from __future__ import annotations

from datetime import date

from cumt_jwxt_cli.errors import QueryError
from cumt_jwxt_cli.models import AppConfig, PeriodTime, ScheduleListData
from cumt_jwxt_cli.schedule.parser import (
    parse_period_times,
    parse_schedule_payload,
    parse_week_dates,
)

SCHEDULE_LIST_PATH = "/kbcx/xskbcx_cxXsgrkb.html"
SCHEDULE_LIST_FALLBACK_PATH = "/kbcx/xskbcx_cxXsKb.html"
PERIOD_TIMES_PATH = "/kbcx/xskbcx_cxRjc.html"
WEEK_DATES_PATH = "/kbcx/xskbcxZccx_cxZcByXnxq.html"

_REFERER = (
    "http://jwxt.cumt.edu.cn/jwglxt/kbcx/"
    "xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default"
)
_AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": _REFERER,
}


def query_schedule_list(config: AppConfig, client: object) -> ScheduleListData:
    """Fetch and parse the JWXT personal schedule list.

    The primary endpoint is attempted first, then the legacy endpoint is used
    when the primary response is not usable JSON.
    """

    list_data = {
        "xnm": config.query.year,
        "xqm": config.query.semester,
        "kzlx": "ck",
        "xsdm": "",
        "kclbdm": "",
    }
    try:
        payload = _request_json(
            client,
            SCHEDULE_LIST_PATH,
            {"gnmkdm": "N2151"},
            list_data,
            "schedule list",
        )
    except QueryError:
        payload = _request_json(
            client,
            SCHEDULE_LIST_FALLBACK_PATH,
            {"gnmkdm": "N2151"},
            {"xnm": config.query.year, "xqm": config.query.semester},
            "schedule list",
        )
    return parse_schedule_payload(payload)


def query_period_times(config: AppConfig, client: object) -> tuple[PeriodTime, ...]:
    """Fetch and parse the JWXT class period time table."""

    payload = _request_json(
        client,
        PERIOD_TIMES_PATH,
        {"gnmkdm": "N2151"},
        {
            "xnm": config.query.year,
            "xqm": config.query.semester,
            "kzlx": "ck",
            "xsdm": "",
            "kclbdm": "",
            "kclxdm": "",
        },
        "period times",
    )
    return parse_period_times(payload)


def query_week_dates(config: AppConfig, client: object) -> dict[int, date]:
    """Fetch and parse the JWXT week-number to Monday date mapping."""

    payload = _request_json(
        client,
        WEEK_DATES_PATH,
        {"gnmkdm": "N2154"},
        {"xnm": config.query.year, "xqm": config.query.semester},
        "week dates",
    )
    return parse_week_dates(payload)


def is_schedule_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    message = str(exc).lower()
    session_markers = (
        "http 901",
        "redirected with http 30",
        "html login page",
    )
    return any(marker in message for marker in session_markers)


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
        _guard_response(response, label)
        return response.json()
    except ValueError as exc:
        raise QueryError(f"JWXT {label} response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _guard_response(response: object, label: str) -> None:
    content_type = ""
    headers = getattr(response, "headers", None)
    if hasattr(headers, "get"):
        content_type = str(headers.get("content-type", "")).lower()
    status_code = getattr(response, "status_code", None)
    # JWXT returns HTTP 901 when the login session has expired.
    if status_code == 901:
        raise QueryError(f"JWXT {label} request failed with HTTP 901.")
    if status_code in {301, 302, 303, 307, 308}:
        raise QueryError(
            f"JWXT {label} request was redirected with HTTP {status_code}."
        )
    if "text/html" in content_type:
        raise QueryError(f"JWXT {label} response looks like an HTML login page.")
