"""Teaching plan query fetch and parsing tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.plan.query_fetch import (
    COURSE_GNMKDM,
    PLAN_COURSE_PATH,
    PLAN_HEADER_PATH,
    PlanFilters,
    build_course_data,
    build_plan_data,
    is_plan_session_query_failure,
    parse_plan_course,
    parse_plan_header,
    query_plan_courses,
    query_plan_headers,
)


def _config() -> SimpleNamespace:
    return SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))


class _FakeResponse:
    def __init__(
        self,
        json_data: object = None,
        *,
        status_code: int = 200,
        content_type: str = "application/json",
        invalid_json: bool = False,
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._invalid_json = invalid_json

    def json(self) -> object:
        if self._invalid_json:
            raise ValueError("not json")
        return self._json_data


class _RecordingClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def _header_item(**overrides: object) -> dict[str, object]:
    item = {
        "jxzxjhxx_id": "PLAN-1",
        "njdm": "2023",
        "zyh": "0810",
        "zyh_id": "0810",
        "zymc": "计算机科学与技术",
        "jg_id": "08",
        "xqmc": "南湖校区",
        "xz": "4",
        "kcs": "112",
        "zdxf": "171.0",
    }
    item.update(overrides)
    return item


def _course_item(**overrides: object) -> dict[str, object]:
    item = {
        "jxzxjhxx_id": "PLAN-1",
        "kch": "M1",
        "kcmc": "高等数学",
        "kcywmc": "Advanced Mathematics",
        "xf": "5.0",
        "zxs": "80",
        "jyxdxnm": "2023",
        "jyxdxqm": "3",
        "yyxdxnxqmc": "2023-2024 第1学期",
        "kcxzmc": "通识必修",
        "kclbmc": "公共基础课",
        "khfsdm": "考试",
        "ksfsdm": "闭卷",
        "kkbmmc": "数学学院",
        "qsjsz": "1-16",
        "xdlx": "zx",
        "shzt": "0",
    }
    item.update(overrides)
    return item


def test_build_plan_data_includes_header_filters() -> None:
    data = build_plan_data(
        PlanFilters(grade="2023", college="08", major="0810", study_type="zx")
    )

    assert data["doType"] == "query"
    assert data["jg_id"] == "08"
    assert data["njdm_id"] == "2023"
    assert data["zyh_id"] == "0810"
    assert data["currentPage_cx"] == "1"
    assert data["queryModel.showCount"] == "200"
    assert data["queryModel.currentPage"] == "1"


def test_build_course_data_always_sends_eight_filter_keys_and_gnmkdm() -> None:
    data = build_course_data(
        PlanFilters(plan_id="PLAN-1", study_year="2023", study_term="3")
    )

    for key in (
        "jyxdxnm",
        "jyxdxqm",
        "yxxdxnm",
        "yxxdxqm",
        "shzt",
        "kch",
        "jxzxjhxx_id",
        "xdlx",
    ):
        assert key in data
    assert data["gnmkdm"] == COURSE_GNMKDM
    assert data["jxzxjhxx_id"] == "PLAN-1"
    assert data["jyxdxnm"] == "2023"
    assert data["jyxdxqm"] == "3"
    assert data["queryModel.sortName"] == "jyxdxnm,jyxdxqm,kch"


def test_query_plan_headers_parses_items_and_uses_get() -> None:
    client = _RecordingClient(
        _FakeResponse({"items": [_header_item()], "totalResult": 1})
    )

    headers = query_plan_headers(
        _config(), client, PlanFilters(grade="2023", college="08", major="0810")
    )

    assert len(headers) == 1
    header = headers[0]
    assert header.plan_id == "PLAN-1"
    assert header.grade == "2023"
    assert header.major_code == "0810"
    assert header.major_name == "计算机科学与技术"
    assert header.college_id == "08"
    assert header.campus == "南湖校区"
    assert header.program_length == "4"
    assert header.course_count == "112"
    assert header.total_credits == "171.0"

    assert len(client.calls) == 1
    assert client.calls[0]["path"] == PLAN_HEADER_PATH
    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["njdm_id"] == "2023"
    assert params["jg_id"] == "08"
    assert params["zyh_id"] == "0810"


def test_query_plan_courses_pages_until_total_result() -> None:
    page_one = [_course_item(kch=f"M{i}") for i in range(200)]
    page_two = [_course_item(kch=f"N{i}") for i in range(50)]
    client = _RecordingClient(
        _FakeResponse({"items": page_one, "totalResult": 250}),
        _FakeResponse({"items": page_two, "totalResult": 250}),
    )

    courses = query_plan_courses(
        _config(), client, PlanFilters(plan_id="PLAN-1"), plan_id="PLAN-1"
    )

    assert len(courses) == 250
    assert [call["path"] for call in client.calls] == [
        PLAN_COURSE_PATH,
        PLAN_COURSE_PATH,
    ]
    first_params = client.calls[0]["params"]
    second_params = client.calls[1]["params"]
    assert isinstance(first_params, dict)
    assert isinstance(second_params, dict)
    assert first_params["queryModel.currentPage"] == "1"
    assert second_params["queryModel.currentPage"] == "2"
    assert first_params["gnmkdm"] == COURSE_GNMKDM


def test_query_plan_courses_stops_when_total_result_reached() -> None:
    client = _RecordingClient(
        _FakeResponse({"items": [_course_item()], "totalResult": 1})
    )

    courses = query_plan_courses(
        _config(), client, PlanFilters(plan_id="PLAN-1"), plan_id="PLAN-1"
    )

    assert len(courses) == 1
    assert len(client.calls) == 1


def test_query_plan_courses_raises_when_pages_exceed_limit() -> None:
    responses = [
        _FakeResponse(
            {
                "items": [_course_item(kch=f"P{page}-{i}") for i in range(200)],
                "totalResult": 2000,
            }
        )
        for page in range(5)
    ]
    client = _RecordingClient(*responses)

    with pytest.raises(QueryError, match="exceeded 5 pages"):
        query_plan_courses(
            _config(), client, PlanFilters(plan_id="PLAN-1"), plan_id="PLAN-1"
        )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_FakeResponse(status_code=901), SessionExpiredError),
        (_FakeResponse(status_code=302), SessionExpiredError),
        (_FakeResponse(status_code=911), QueryError),
        (_FakeResponse(content_type="text/html"), SessionExpiredError),
    ],
)
def test_query_plan_headers_maps_transport_failures(
    response: _FakeResponse, expected: type[Exception]
) -> None:
    client = _RecordingClient(response)

    with pytest.raises(expected):
        query_plan_headers(_config(), client, PlanFilters(grade="2023"))


def test_query_plan_headers_rejects_invalid_json() -> None:
    client = _RecordingClient(_FakeResponse(invalid_json=True))

    with pytest.raises(QueryError, match="not valid JSON"):
        query_plan_headers(_config(), client, PlanFilters(grade="2023"))


@pytest.mark.parametrize(
    "payload",
    [[], {"foo": 1}, {"items": "bad"}],
)
def test_query_plan_headers_rejects_unexpected_json(payload: object) -> None:
    client = _RecordingClient(_FakeResponse(payload))

    with pytest.raises(ParseError):
        query_plan_headers(_config(), client, PlanFilters(grade="2023"))


def test_parse_plan_header_requires_plan_id() -> None:
    with pytest.raises(ParseError, match="jxzxjhxx_id"):
        parse_plan_header({"zymc": "计算机科学与技术"})


def test_parse_plan_course_tolerates_missing_optional_fields() -> None:
    course = parse_plan_course({"kcmc": "高等数学"})

    assert course.course_name == "高等数学"
    assert course.course_code is None
    assert course.credits is None
    assert course.study_term is None


def test_parse_plan_course_requires_code_or_name() -> None:
    with pytest.raises(ParseError):
        parse_plan_course({"xf": "2.0"})


def test_is_plan_session_query_failure_only_matches_session_expiry() -> None:
    assert is_plan_session_query_failure(SessionExpiredError("expired"))
    assert not is_plan_session_query_failure(QueryError("query"))
