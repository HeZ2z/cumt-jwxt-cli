"""Course query fetch tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.courses.query_fetch import (
    LIST_PATH,
    PAGE_PATH,
    CourseQueryOptions,
    build_query_data,
    is_course_session_query_failure,
    parse_widget_guid,
    query_course_sessions,
)
from cumt_jwxt_cli.courses.service import run_course_query
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import CourseSession

_GUID = "A1B2C3D4E5F6"


def _config(**overrides: object) -> SimpleNamespace:
    base = SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _page_html(guid: str = _GUID) -> str:
    return f'<html><div data-func_widget_guid="{guid}"></div></html>'


class _FakeResponse:
    def __init__(
        self,
        *,
        json_data: object = None,
        text: str = "",
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self._json_data = json_data
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self) -> object:
        return self._json_data


class _RecordingClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"method": "get", "path": path, **kwargs})
        return self._responses.pop(0)

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"method": "post", "path": path, **kwargs})
        return self._responses.pop(0)


def _options(**overrides: object) -> CourseQueryOptions:
    values: dict[str, object] = {"teacher": "张三", "limit": 5}
    values.update(overrides)
    return CourseQueryOptions(**values)  # type: ignore[arg-type]


def test_parse_widget_guid_reads_data_attribute() -> None:
    assert parse_widget_guid(_page_html()) == _GUID


def test_parse_widget_guid_falls_back_to_regex() -> None:
    html = f"<script>var func_widget_guid = '{_GUID}';</script>"

    assert parse_widget_guid(html) == _GUID


@pytest.mark.parametrize("html", ["", "<html><div></div></html>"])
def test_parse_widget_guid_raises_when_missing(html: str) -> None:
    with pytest.raises(ParseError, match="Course query page"):
        parse_widget_guid(html)


def test_build_query_data_maps_filters() -> None:
    data = build_query_data(
        _config(),
        _options(
            course="M12345",
            teacher="张三",
            room="博1-A203",
            weekday=3,
            periods="1-2",
            weeks="1",
        ),
    )

    assert data == {
        "xnm": "2026",
        "xqm": "3",
        "kch_id": "M12345",
        "js": "张三",
        "jxcd": "博1-A203",
        "xqj": "3",
        "skjc": "1-2",
        "qsjsz": "1",
    }


def test_build_query_data_omits_absent_filters() -> None:
    data = build_query_data(_config(), CourseQueryOptions(teacher="张三"))

    assert data == {"xnm": "2026", "xqm": "3", "js": "张三"}


def test_query_course_sessions_gets_page_then_posts_with_guid() -> None:
    payload = {
        "items": [
            {
                "kch": "M12345",
                "kcmc": "高等数学",
                "xf": "3.0",
                "xm": "张三",
                "xqj": "1",
                "skjc": "1-2",
                "qsjsz": "1-16",
                "cdmc": "博1-A203",
                "jxbrs": "120",
                "xkrs": "60",
                "jxdd": "博1-A203",
            }
        ],
        "totalResult": 1,
    }
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data=payload),
    )

    result = query_course_sessions(_config(), client, _options())

    assert result.total == 1
    assert result.sessions[0] == CourseSession(
        course_code="M12345",
        course_name="高等数学",
        credits="3.0",
        total_hours=None,
        weekly_hours=None,
        course_nature=None,
        teacher_name="张三",
        teaching_class=None,
        class_composition=None,
        class_size="120",
        enrolled_count="60",
        college=None,
        campus=None,
        building=None,
        room="博1-A203",
        weekday="1",
        periods="1-2",
        start_week="1-16",
        schedule_text=None,
        location_text="博1-A203",
    )

    assert [call["method"] for call in client.calls] == ["get", "post"]
    assert client.calls[0]["path"] == PAGE_PATH
    assert client.calls[0]["params"] == {"gnmkdm": "N219904", "layout": "default"}
    assert client.calls[1]["path"] == LIST_PATH
    assert client.calls[1]["params"] == {"func_widget_guid": _GUID}
    assert client.calls[1]["data"]["js"] == "张三"
    assert client.calls[1]["data"]["queryModel.currentPage"] == "1"
    assert client.calls[1]["data"]["queryModel.showCount"] == "5"


def test_query_course_sessions_pages_until_total_when_limit_is_zero() -> None:
    first_page = [{"kch": f"C{index}"} for index in range(200)]
    second_page = [{"kch": f"C{index}"} for index in range(200, 250)]
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data={"items": first_page, "totalResult": 250}),
        _FakeResponse(json_data={"items": second_page, "totalResult": 250}),
    )

    result = query_course_sessions(_config(), client, _options(limit=0))

    assert len(result.sessions) == 250
    assert result.total == 250
    posts = [call for call in client.calls if call["method"] == "post"]
    assert [call["data"]["queryModel.currentPage"] for call in posts] == ["1", "2"]
    assert all(call["data"]["queryModel.showCount"] == "200" for call in posts)


def test_query_course_sessions_does_not_treat_get_empty_result_as_data() -> None:
    payload = {"items": [{"kcmc": "高等数学"}], "totalResult": 1}
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data=payload),
    )

    result = query_course_sessions(_config(), client, _options())

    assert len(result.sessions) == 1
    # Only the page GET is allowed; the data request must be a POST.
    assert [call["method"] for call in client.calls] == ["get", "post"]


def test_query_course_sessions_raises_on_901_from_page() -> None:
    client = _RecordingClient(_FakeResponse(status_code=901))

    with pytest.raises(SessionExpiredError, match="901"):
        query_course_sessions(_config(), client, _options())


def test_query_course_sessions_raises_on_html_list_response() -> None:
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(content_type="text/html"),
    )

    with pytest.raises(SessionExpiredError, match="HTML login"):
        query_course_sessions(_config(), client, _options())


def test_query_course_sessions_raises_on_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = SimpleNamespace(
        get=lambda *args, **kwargs: _FakeResponse(
            text=_page_html(), content_type="text/html"
        ),
        post=lambda *args, **kwargs: BadResponse(),
    )

    with pytest.raises(QueryError, match="not valid JSON"):
        query_course_sessions(_config(), client, _options())


def test_query_course_sessions_raises_on_invalid_payload_shape() -> None:
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data={"rows": []}),
    )

    with pytest.raises(ParseError, match="items"):
        query_course_sessions(_config(), client, _options())


def test_query_course_sessions_models_missing_fields_as_none() -> None:
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data={"items": [{}], "totalResult": 1}),
    )

    session = query_course_sessions(_config(), client, _options()).sessions[0]

    for field in (
        "course_code",
        "course_name",
        "credits",
        "teacher_name",
        "room",
        "weekday",
        "periods",
        "location_text",
    ):
        assert getattr(session, field) is None


def test_query_course_sessions_uses_one_page_for_positive_limit() -> None:
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data={"items": [{"kch": "C1"}], "totalResult": 900}),
    )

    result = query_course_sessions(_config(), client, _options(limit=5))

    assert result.total == 900
    assert [call["method"] for call in client.calls] == ["get", "post"]


def test_query_course_sessions_fetches_enough_pages_for_large_limit() -> None:
    pages = [
        [{"kch": f"C{page * 200 + index}"} for index in range(200)] for page in range(3)
    ]
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        *[
            _FakeResponse(json_data={"items": page, "totalResult": 600})
            for page in pages
        ],
    )

    result = query_course_sessions(_config(), client, _options(limit=500))

    assert len(result.sessions) == 600
    posts = [call for call in client.calls if call["method"] == "post"]
    assert [call["data"]["queryModel.currentPage"] for call in posts] == [
        "1",
        "2",
        "3",
    ]


def test_run_course_query_sorts_and_applies_limit() -> None:
    payload = {
        "items": [
            {"kch": "C3", "kcmc": "周三课", "xqj": "3", "skjc": "3-4"},
            {"kch": "C1", "kcmc": "周一课", "xqj": "1", "skjc": "5-6"},
            {"kch": "C2", "kcmc": "周一早", "xqj": "1", "skjc": "1-2"},
        ],
        "totalResult": 3,
    }
    client = _RecordingClient(
        _FakeResponse(text=_page_html(), content_type="text/html"),
        _FakeResponse(json_data=payload),
    )

    result = run_course_query(_config(), client, _options(limit=2))

    assert [session.course_name for session in result.sessions] == ["周一早", "周一课"]
    assert result.total == 3


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (SessionExpiredError("request failed with HTTP 901"), True),
        (SessionExpiredError("looks like an HTML login page"), True),
        (QueryError("response is not valid JSON"), False),
    ],
)
def test_is_course_session_query_failure(exc: QueryError, expected: bool) -> None:
    assert is_course_session_query_failure(exc) is expected
