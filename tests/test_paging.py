"""Pagination helper tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.client.paging import fetch_all_items
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError


class _FakeResponse:
    def __init__(
        self,
        payload: object = None,
        *,
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self) -> object:
        return self._payload


class _QueuedClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def _page_items(start: int, count: int) -> list[dict[str, str]]:
    return [{"kch": f"C{index:04d}"} for index in range(start, start + count)]


def test_fetch_all_items_returns_single_page() -> None:
    client = _QueuedClient(_FakeResponse({"items": _page_items(0, 2)}))

    items = fetch_all_items(
        client,
        "/list",
        data={},
        label="grade list",
    )

    assert items == _page_items(0, 2)
    assert len(client.calls) == 1
    assert client.calls[0]["data"] == {
        "queryModel.showCount": "100",
        "queryModel.currentPage": "1",
    }


def test_fetch_all_items_concatenates_pages() -> None:
    client = _QueuedClient(
        _FakeResponse({"items": _page_items(0, 2)}),
        _FakeResponse({"items": _page_items(2, 1)}),
    )

    items = fetch_all_items(
        client,
        "/list",
        data={"xnm": "2025"},
        label="exam list",
        page_size=2,
    )

    assert items == _page_items(0, 3)
    assert [call["data"]["queryModel.currentPage"] for call in client.calls] == [
        "1",
        "2",
    ]
    assert all(call["data"]["xnm"] == "2025" for call in client.calls)


def test_fetch_all_items_stops_when_total_result_reached() -> None:
    client = _QueuedClient(
        _FakeResponse({"items": _page_items(0, 2), "totalResult": 2}),
        _FakeResponse({"items": _page_items(2, 2)}),
    )

    items = fetch_all_items(
        client,
        "/list",
        data={},
        label="grade list",
        page_size=2,
    )

    assert items == _page_items(0, 2)
    assert len(client.calls) == 1


def test_fetch_all_items_does_not_duplicate_when_server_ignores_paging() -> None:
    repeated = _page_items(0, 2)
    client = _QueuedClient(
        _FakeResponse({"items": repeated}),
        _FakeResponse({"items": repeated}),
    )

    items = fetch_all_items(
        client,
        "/list",
        data={},
        label="grade list",
        page_size=2,
    )

    assert items == repeated
    assert len(client.calls) == 2


def test_fetch_all_items_refuses_to_truncate_at_max_pages() -> None:
    client = _QueuedClient(
        _FakeResponse({"items": _page_items(0, 1)}),
        _FakeResponse({"items": _page_items(1, 1)}),
    )

    with pytest.raises(QueryError, match="exceeded 2 pages"):
        fetch_all_items(
            client,
            "/list",
            data={},
            label="grade list",
            page_size=1,
            max_pages=2,
        )


def test_fetch_all_items_continues_when_server_caps_page_size() -> None:
    responses = [
        _FakeResponse({"items": _page_items(index * 20, 20), "totalResult": 150})
        for index in range(7)
    ]
    responses.append(_FakeResponse({"items": _page_items(140, 10), "totalResult": 150}))
    client = _QueuedClient(*responses)

    items = fetch_all_items(
        client,
        "/list",
        data={},
        label="grade list",
        page_size=100,
    )

    assert len(items) == 150
    assert len(client.calls) == 8
    assert [call["data"]["queryModel.currentPage"] for call in client.calls] == [
        str(page) for page in range(1, 9)
    ]


def test_fetch_all_items_raises_when_repeated_page_below_total() -> None:
    repeated = _page_items(0, 2)
    client = _QueuedClient(
        _FakeResponse({"items": repeated, "totalResult": 150}),
        _FakeResponse({"items": repeated, "totalResult": 150}),
    )

    with pytest.raises(QueryError, match="ended early at 2 of 150 items"):
        fetch_all_items(
            client,
            "/list",
            data={},
            label="grade list",
            page_size=2,
        )


def test_fetch_all_items_raises_when_empty_page_below_total() -> None:
    client = _QueuedClient(
        _FakeResponse({"items": _page_items(0, 2), "totalResult": 150}),
        _FakeResponse({"items": [], "totalResult": 150}),
    )

    with pytest.raises(QueryError, match="ended early at 2 of 150 items"):
        fetch_all_items(
            client,
            "/list",
            data={},
            label="grade list",
            page_size=2,
        )


def test_fetch_all_items_stops_on_short_page_without_total() -> None:
    client = _QueuedClient(
        _FakeResponse({"items": _page_items(0, 2)}),
        _FakeResponse({"items": _page_items(2, 2)}),
    )

    items = fetch_all_items(
        client,
        "/list",
        data={},
        label="grade list",
        page_size=100,
    )

    assert items == _page_items(0, 2)
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(status_code=901),
        _FakeResponse(status_code=302),
        _FakeResponse(content_type="text/html"),
    ],
)
def test_fetch_all_items_propagates_session_expiry(response: _FakeResponse) -> None:
    client = _QueuedClient(response)

    with pytest.raises(SessionExpiredError):
        fetch_all_items(
            client,
            "/list",
            data={},
            label="grade list",
        )


def test_fetch_all_items_rejects_unexpected_payload_shape() -> None:
    client = _QueuedClient(_FakeResponse({"rows": []}))

    with pytest.raises(ParseError, match="items"):
        fetch_all_items(client, "/list", data={}, label="grade list")


def test_fetch_all_items_wraps_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = SimpleNamespace(get=lambda key, default="": "application/json")

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = _QueuedClient(BadResponse())  # type: ignore[arg-type]

    with pytest.raises(QueryError, match="not valid JSON"):
        fetch_all_items(client, "/list", data={}, label="grade list")
