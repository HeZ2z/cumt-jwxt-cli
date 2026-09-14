"""Schedule query fetch tests."""

from datetime import date
from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.errors import QueryError
from cumt_jwxt_cli.models import PeriodTime, ScheduleListData
from cumt_jwxt_cli.schedule.query_fetch import (
    is_schedule_session_query_failure,
    query_period_times,
    query_schedule_list,
    query_week_dates,
)


def _config(**overrides: object) -> SimpleNamespace:
    base = SimpleNamespace(query=SimpleNamespace(year="2025", semester="3"))
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class _FakeResponse:
    def __init__(
        self,
        json_data: object = None,
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self) -> object:
        return self._json_data


class _SequencedClient:
    """Return queued responses and record the requests made."""

    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def test_query_schedule_list_returns_parsed_data() -> None:
    payload = {
        "kbList": [
            {"kcmc": "高数", "kch": "M001", "xqj": "1", "jcs": "1-2", "zcd": "1周"}
        ],
        "sjkList": [],
    }
    client = _SequencedClient(_FakeResponse(json_data=payload))

    result = query_schedule_list(_config(), client)

    assert isinstance(result, ScheduleListData)
    assert result.lessons[0].course_name == "高数"
    assert client.calls[0]["path"] == "/kbcx/xskbcx_cxXsgrkb.html"


def test_query_schedule_list_falls_back_on_html_response() -> None:
    payload = {
        "kbList": [
            {"kcmc": "高数", "kch": "M001", "xqj": "1", "jcs": "1", "zcd": "1周"}
        ]
    }
    client = _SequencedClient(
        _FakeResponse(status_code=200, content_type="text/html"),
        _FakeResponse(json_data=payload),
    )

    result = query_schedule_list(_config(), client)

    assert result.lessons[0].course_name == "高数"
    assert [call["path"] for call in client.calls] == [
        "/kbcx/xskbcx_cxXsgrkb.html",
        "/kbcx/xskbcx_cxXsKb.html",
    ]


def test_query_schedule_list_raises_when_both_attempts_fail() -> None:
    client = _SequencedClient(
        _FakeResponse(status_code=200, content_type="text/html"),
        _FakeResponse(status_code=901),
    )

    with pytest.raises(QueryError, match="901"):
        query_schedule_list(_config(), client)


def test_query_schedule_list_raises_on_901() -> None:
    client = _SequencedClient(
        _FakeResponse(status_code=901), _FakeResponse(status_code=901)
    )

    with pytest.raises(QueryError, match="901"):
        query_schedule_list(_config(), client)


def test_query_schedule_list_raises_on_redirect() -> None:
    client = _SequencedClient(
        _FakeResponse(status_code=302), _FakeResponse(status_code=302)
    )

    with pytest.raises(QueryError, match="redirected with HTTP 302"):
        query_schedule_list(_config(), client)


def test_query_schedule_list_raises_on_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = _SequencedClient(BadResponse(), BadResponse())  # type: ignore[arg-type]

    with pytest.raises(QueryError, match="not valid JSON"):
        query_schedule_list(_config(), client)


def test_query_schedule_list_raises_on_invalid_response_object() -> None:
    client = _SequencedClient(None, None)  # type: ignore[arg-type]

    with pytest.raises(QueryError, match="invalid response"):
        query_schedule_list(_config(), client)


def test_query_period_times_returns_records() -> None:
    payload = [{"jcmc": "1", "qssj": "08:00", "jssj": "08:50", "rsdmc": "上午"}]
    client = _SequencedClient(_FakeResponse(json_data=payload))

    result = query_period_times(_config(), client)

    assert result == (
        PeriodTime(period="1", start="08:00", end="08:50", section="上午"),
    )
    assert client.calls[0]["path"] == "/kbcx/xskbcx_cxRjc.html"


def test_query_week_dates_returns_monday_mapping() -> None:
    payload = [{"zs": "1", "zcrq": "1(2025-09-01~2025-09-07)"}]
    client = _SequencedClient(_FakeResponse(json_data=payload))

    result = query_week_dates(_config(), client)

    assert result == {1: date(2025, 9, 1)}
    assert client.calls[0]["path"] == "/kbcx/xskbcxZccx_cxZcByXnxq.html"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("request failed with HTTP 901", True),
        ("request was redirected with HTTP 302", True),
        ("looks like an HTML login page", True),
        ("response is not valid JSON", False),
        ("invalid response object", False),
        ("request failed after retry attempts", False),
    ],
)
def test_is_schedule_session_query_failure(message: str, expected: bool) -> None:
    assert is_schedule_session_query_failure(QueryError(message)) is expected
