"""Academic status transport and statistics merge tests."""

import pytest

from cumt_jwxt_cli.academic.query_fetch import (
    ACADEMIC_PAGE_PATH,
    PROPERTY_GPA_PATH,
    PROPERTY_WEIGHTED_PATH,
    parse_property_items,
    query_academic_summary,
)
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError

_PAGE_HTML = """
<html><body>
<div id="alertBox">统计时间：2026-11-21 全部课程GPA：3.2 计划课程 总：10 通过：8</div>
<input id="xh_id" value="20230001" />
<li xfyqjd_id='1' fxfyqjd_id=''>
<span id='p1' yqzdxf='10' yxxf='10' sftg='1'>课程</span></li>
</body></html>
"""


class FakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        status_code: int = 200,
        payload: object = None,
        content_type: str = "text/html",
    ) -> None:
        self.text = text
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": content_type}

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, **kwargs: object) -> object:
        params = kwargs.get("params")
        assert isinstance(params, dict)
        self.calls.append((path, params))
        response = self._responses[path]
        if isinstance(response, Exception):
            raise response
        return response


def _page_response() -> FakeResponse:
    return FakeResponse(text=_PAGE_HTML)


def _json_response(payload: object) -> FakeResponse:
    return FakeResponse(payload=payload, content_type="application/json")


def test_query_academic_summary_merges_property_statistics() -> None:
    client = FakeClient(
        {
            ACADEMIC_PAGE_PATH: _page_response(),
            PROPERTY_GPA_PATH: _json_response(
                {
                    "items": [
                        {
                            "kcxzdm": "k1",
                            "kcxzmc": "通识教育必修课",
                            "gpa": "2.18",
                            "hdxf": "37.5",
                        }
                    ]
                }
            ),
            PROPERTY_WEIGHTED_PATH: _json_response(
                {
                    "items": [
                        {
                            "kcxzdm": "k1",
                            "kcxzmc": "通识教育必修课",
                            "jqpjf": "71.39",
                            "hdxf": "37.5",
                        },
                        {
                            "kcxzdm": "k2",
                            "kcxzmc": "通识教育选修课",
                            "jqpjf": "80.0",
                            "hdxf": "2.0",
                        },
                    ]
                }
            ),
        }
    )

    result = query_academic_summary(None, client)

    assert result.overview.plan_total == "10"
    assert result.overview.plan_passed == "8"
    assert len(result.plan_nodes) == 1
    assert len(result.property_stats) == 2
    first, second = result.property_stats
    assert first.property_code == "k1"
    assert first.gpa == "2.18"
    assert first.weighted_average == "71.39"
    assert first.earned_credits == "37.5"
    assert second.property_code == "k2"
    assert second.gpa is None
    assert second.weighted_average == "80.0"

    paths = [path for path, _params in client.calls]
    assert paths == [ACADEMIC_PAGE_PATH, PROPERTY_GPA_PATH, PROPERTY_WEIGHTED_PATH]
    assert client.calls[0][1]["gnmkdm"] == "N105515"
    assert client.calls[1][1] == {"doType": "query", "xh_id": "20230001"}


def test_query_academic_summary_degrades_when_property_stats_fail() -> None:
    client = FakeClient(
        {
            ACADEMIC_PAGE_PATH: _page_response(),
            PROPERTY_GPA_PATH: QueryError("stats failed"),
            PROPERTY_WEIGHTED_PATH: _json_response({"items": []}),
        }
    )

    result = query_academic_summary(None, client)

    assert result.overview.plan_total == "10"
    assert result.property_stats == ()


def test_query_academic_summary_degrades_when_second_stats_fail() -> None:
    client = FakeClient(
        {
            ACADEMIC_PAGE_PATH: _page_response(),
            PROPERTY_GPA_PATH: _json_response({"items": []}),
            PROPERTY_WEIGHTED_PATH: ParseError("bad payload"),
        }
    )

    result = query_academic_summary(None, client)

    assert result.property_stats == ()


def test_query_academic_summary_propagates_session_expiry_from_stats() -> None:
    client = FakeClient(
        {
            ACADEMIC_PAGE_PATH: _page_response(),
            PROPERTY_GPA_PATH: SessionExpiredError("expired"),
            PROPERTY_WEIGHTED_PATH: _json_response({"items": []}),
        }
    )

    with pytest.raises(SessionExpiredError):
        query_academic_summary(None, client)


def test_query_academic_summary_retries_redirected_page_as_session_failure() -> None:
    client = FakeClient({ACADEMIC_PAGE_PATH: FakeResponse(status_code=302)})

    with pytest.raises(SessionExpiredError):
        query_academic_summary(None, client)


def test_query_academic_summary_skips_stats_without_xh_id() -> None:
    page = _PAGE_HTML.replace('<input id="xh_id" value="20230001" />', "")
    client = FakeClient({ACADEMIC_PAGE_PATH: FakeResponse(text=page)})

    result = query_academic_summary(None, client)

    assert result.overview.plan_total == "10"
    assert result.property_stats == ()
    assert [path for path, _params in client.calls] == [ACADEMIC_PAGE_PATH]


@pytest.mark.parametrize("payload", [[], {"foo": 1}, {"items": "bad"}])
def test_parse_property_items_rejects_unexpected_json(payload: object) -> None:
    with pytest.raises(ParseError):
        parse_property_items(payload)
