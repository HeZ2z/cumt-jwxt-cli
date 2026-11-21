"""Exam query fetch tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.errors import QueryError, SessionExpiredError
from cumt_jwxt_cli.exams.query_fetch import (
    is_exam_session_query_failure,
    query_exam_list,
)
from cumt_jwxt_cli.models import ExamInfo


def _config(**overrides: object) -> SimpleNamespace:
    base = SimpleNamespace(query=SimpleNamespace(year="2025", semester="3"))
    for k, v in overrides.items():
        setattr(base, k, v)
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


def test_query_exam_list_returns_parsed_exams() -> None:
    items = [
        {"kch": "CODE1", "kcmc": "Course 1"},
        {"kch": "CODE2", "kcmc": "Course 2"},
    ]
    response = _FakeResponse(json_data={"items": items})
    client = SimpleNamespace(post=lambda *args, **kwargs: response)
    exams = query_exam_list(_config(), client)

    assert exams == [
        ExamInfo(course_code="CODE1", course_name="Course 1"),
        ExamInfo(course_code="CODE2", course_name="Course 2"),
    ]


def test_query_exam_list_raises_on_901() -> None:
    response = _FakeResponse(status_code=901)
    client = SimpleNamespace(post=lambda *args, **kwargs: response)

    with pytest.raises(SessionExpiredError, match="901"):
        query_exam_list(_config(), client)


def test_query_exam_list_raises_on_redirect_response() -> None:
    response = _FakeResponse(status_code=302)
    client = SimpleNamespace(post=lambda *args, **kwargs: response)

    with pytest.raises(SessionExpiredError, match="redirected with HTTP 302"):
        query_exam_list(_config(), client)


def test_query_exam_list_raises_on_html_response() -> None:
    response = _FakeResponse(status_code=200, content_type="text/html")
    client = SimpleNamespace(post=lambda *args, **kwargs: response)

    with pytest.raises(SessionExpiredError, match="HTML login"):
        query_exam_list(_config(), client)


def test_query_exam_list_merges_pages_before_parsing() -> None:
    first_page = [
        {"kch": f"CODE{index}", "kcmc": f"Course {index}"} for index in range(100)
    ]
    second_page = [{"kch": "CODE100", "kcmc": "Course 100"}]

    class PagedClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def post(self, path: str, **kwargs: object) -> _FakeResponse:
            data = kwargs["data"]
            assert isinstance(data, dict)
            self.calls.append(data)
            payload = first_page if len(self.calls) == 1 else second_page
            return _FakeResponse(json_data={"items": payload})

    client = PagedClient()
    exams = query_exam_list(_config(), client)

    assert len(exams) == 101
    assert exams[-1] == ExamInfo(course_code="CODE100", course_name="Course 100")
    assert [call["queryModel.currentPage"] for call in client.calls] == ["1", "2"]
    assert all(call["queryModel.showCount"] == "100" for call in client.calls)


def test_query_exam_list_raises_on_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = SimpleNamespace(post=lambda *args, **kwargs: BadResponse())

    with pytest.raises(QueryError, match="not valid JSON"):
        query_exam_list(_config(), client)


def test_query_exam_list_raises_on_invalid_response_object() -> None:
    client = SimpleNamespace(post=lambda *args, **kwargs: None)

    with pytest.raises(QueryError, match="invalid response"):
        query_exam_list(_config(), client)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (SessionExpiredError("request failed with HTTP 901"), True),
        (SessionExpiredError("request was redirected with HTTP 302"), True),
        (SessionExpiredError("looks like an HTML login page"), True),
        (QueryError("response is not valid JSON"), False),
        (QueryError("invalid response object"), False),
        (QueryError("request failed after retry attempts"), False),
    ],
)
def test_is_exam_session_query_failure(exc: QueryError, expected: bool) -> None:
    assert is_exam_session_query_failure(exc) is expected
