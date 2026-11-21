"""Free classroom query fetch tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.classrooms.query_fetch import (
    ClassroomQueryOptions,
    build_query_data,
    is_classroom_session_query_failure,
    parse_clock,
    parse_date,
    query_classrooms,
)
from cumt_jwxt_cli.classrooms.service import run_classroom_query
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import FreeClassroom


def _config(**overrides: object) -> SimpleNamespace:
    base = SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))
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


class _RecordingClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def _options(**overrides: object) -> ClassroomQueryOptions:
    values: dict[str, object] = {
        "date": "2026-11-23",
        "start": "08:00",
        "end": "09:40",
        "campus": "nanhu",
        "building": "博1",
        "min_seats": 50,
        "max_seats": 100,
        "lendable": True,
        "limit": 5,
    }
    values.update(overrides)
    return ClassroomQueryOptions(**values)  # type: ignore[arg-type]


def test_build_query_data_uses_verified_field_contract() -> None:
    data = build_query_data(_config(), _options())

    assert data["xnm"] == "2026"
    assert data["xqm"] == "3"
    assert data["xqh_id"] == "2"
    assert data["jyfs"] == "1"
    assert data["qssj"] == "2026-11-23"
    assert data["jssj"] == "2026-11-23"
    assert data["qssd"] == "08:00"
    assert data["jssd"] == "09:40"
    assert data["lh"] == "博1"
    assert data["qszws"] == "50"
    assert data["jszws"] == "100"
    assert data["sfkjy"] == "1"


@pytest.mark.parametrize(
    ("campus", "expected"),
    [("all", ""), ("nanhu", "2"), ("wenchang", "1")],
)
def test_build_query_data_maps_campus(campus: str, expected: str) -> None:
    data = build_query_data(_config(), _options(campus=campus, lendable=False))

    assert data["xqh_id"] == expected
    assert "sfkjy" not in data


def test_build_query_data_omits_time_filters_when_absent() -> None:
    data = build_query_data(_config(), _options(start=None, end=None))

    assert data["qssd"] == ""
    assert data["jssd"] == ""


def test_query_classrooms_parses_items_and_yes_no() -> None:
    payload = {
        "items": [
            {
                "cdmc": "博1-A203",
                "cdbh": "A203",
                "jxlmc": "博1",
                "lch": "2",
                "xqmc": "南湖校区",
                "cdlbmc": "公用多媒体",
                "zws": "170",
                "kszws1": "165",
                "sfkjy": "是",
                "sfkpk": "否",
            },
            {
                "cdmc": "博1-A204",
                "sjzws": "30",
                "sfkjy": "未知",
            },
        ],
        "totalResult": 2,
    }
    client = _RecordingClient(_FakeResponse(json_data=payload))

    result = query_classrooms(_config(), client, _options(limit=0))

    assert result.total == 2
    assert result.classrooms[0] == FreeClassroom(
        room_name="博1-A203",
        room_code="A203",
        building="博1",
        floor="2",
        campus="南湖校区",
        category="公用多媒体",
        seats="170",
        exam_seats="165",
        lendable=True,
        schedulable=False,
    )
    assert result.classrooms[1].seats == "30"
    assert result.classrooms[1].lendable is None
    assert result.classrooms[1].schedulable is None


def test_query_classrooms_walks_pages_until_total() -> None:
    first_page = [{"cdmc": f"房{index}", "cdbh": f"C{index}"} for index in range(500)]
    second_page = [
        {"cdmc": f"房{index}", "cdbh": f"C{index}"} for index in range(500, 600)
    ]
    client = _RecordingClient(
        _FakeResponse(json_data={"items": first_page, "totalResult": 600}),
        _FakeResponse(json_data={"items": second_page, "totalResult": 600}),
    )

    result = query_classrooms(_config(), client, _options(limit=0))

    assert len(result.classrooms) == 600
    assert result.total == 600
    assert [call["data"]["queryModel.currentPage"] for call in client.calls] == [
        "1",
        "2",
    ]
    assert all(call["data"]["queryModel.showCount"] == "500" for call in client.calls)


def test_query_classrooms_uses_requested_params_and_page_size() -> None:
    payload = {"items": [{"cdmc": "房1"}], "totalResult": 559}
    client = _RecordingClient(_FakeResponse(json_data=payload))

    result = query_classrooms(_config(), client, _options(limit=5))

    assert result.total == 559
    assert len(result.classrooms) == 1
    assert client.calls[0]["path"] == "/cdjy/cdjy_cxKxcdlb.html"
    assert client.calls[0]["data"]["queryModel.showCount"] == "500"
    assert client.calls[0]["params"] == {"doType": "query", "gnmkdm": "N2155"}


def test_run_classroom_query_sorts_and_applies_limit() -> None:
    payload = {
        "items": [
            {
                "cdmc": "晚",
                "jxlmc": "博1",
                "lch": "10",
                "xqmc": "南湖校区",
                "cdbh": "3",
            },
            {"cdmc": "早", "jxlmc": "博1", "lch": "2", "xqmc": "南湖校区", "cdbh": "2"},
            {"cdmc": "缺层", "jxlmc": "博1", "xqmc": "南湖校区", "cdbh": "1"},
        ],
        "totalResult": 3,
    }
    client = _RecordingClient(_FakeResponse(json_data=payload))

    result = run_classroom_query(_config(), client, _options(limit=2))

    assert [room.room_name for room in result.classrooms] == ["早", "晚"]
    assert result.total == 3


def test_query_classrooms_raises_on_901() -> None:
    client = _RecordingClient(_FakeResponse(status_code=901))

    with pytest.raises(SessionExpiredError, match="901"):
        query_classrooms(_config(), client, _options())


def test_query_classrooms_raises_on_html_response() -> None:
    client = _RecordingClient(_FakeResponse(content_type="text/html"))

    with pytest.raises(SessionExpiredError, match="HTML login"):
        query_classrooms(_config(), client, _options())


def test_query_classrooms_raises_on_invalid_payload_shape() -> None:
    client = _RecordingClient(_FakeResponse(json_data={"rows": []}))

    with pytest.raises(ParseError, match="items"):
        query_classrooms(_config(), client, _options())


def test_query_classrooms_raises_on_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = SimpleNamespace(post=lambda *args, **kwargs: BadResponse())

    with pytest.raises(QueryError, match="not valid JSON"):
        query_classrooms(_config(), client, _options())


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (SessionExpiredError("request failed with HTTP 901"), True),
        (SessionExpiredError("looks like an HTML login page"), True),
        (QueryError("response is not valid JSON"), False),
    ],
)
def test_is_classroom_session_query_failure(exc: QueryError, expected: bool) -> None:
    assert is_classroom_session_query_failure(exc) is expected


def test_parse_date_rejects_invalid_values() -> None:
    assert parse_date("2026-11-23") == "2026-11-23"

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_date("2026/11/23")
    with pytest.raises(ValueError, match="无效日期"):
        parse_date("2026-02-30")


def test_parse_clock_rejects_invalid_values() -> None:
    assert parse_clock("08:00") == "08:00"

    with pytest.raises(ValueError, match="HH:MM"):
        parse_clock("8:00")
    with pytest.raises(ValueError, match="无效时刻"):
        parse_clock("25:00")
