"""Tests for resolving the current JWXT term from the classroom page."""

from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.client.term as term_module
from cumt_jwxt_cli.errors import SessionExpiredError


class FakeClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, **kwargs: object) -> object:
        self.calls.append((path, dict(kwargs.get("params", {}))))  # type: ignore[arg-type]
        return self.response


def _response(
    *,
    status_code: int = 200,
    text: str = "",
    content_type: str = "text/html;charset=utf-8",
) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=status_code,
        headers={"content-type": content_type},
        text=text,
    )


def _page(year: str = "2026", semester: str = "3") -> str:
    return (
        "<html><body>"
        f'<input type="hidden" id="xnm" value="{year}">'
        f'<input type="hidden" id="xqm" value="{semester}">'
        "</body></html>"
    )


def test_resolve_current_term_reads_hidden_inputs() -> None:
    client = FakeClient(_response(text=_page()))

    assert term_module.resolve_current_term(client) == ("2026", "3")
    assert client.calls == [
        (
            term_module.TERM_PAGE_PATH,
            {"gnmkdm": "N2155", "layout": "default"},
        )
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<html><body>no inputs</body></html>", None),
        (_page(year="26"), None),
        (_page(year="abcd"), None),
        (_page(semester="4"), None),
        (_page(semester=""), None),
        ("", None),
        ("   ", None),
    ],
)
def test_resolve_current_term_returns_none_for_unusable_pages(
    text: str, expected: tuple[str, str] | None
) -> None:
    client = FakeClient(_response(text=text))

    assert term_module.resolve_current_term(client) is expected


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308, 901])
def test_resolve_current_term_raises_on_expired_session(status_code: int) -> None:
    client = FakeClient(_response(status_code=status_code, text=_page()))

    with pytest.raises(SessionExpiredError):
        term_module.resolve_current_term(client)


def test_resolve_current_term_accepts_html_success_response() -> None:
    client = FakeClient(_response(text=_page(semester="12")))

    assert term_module.resolve_current_term(client) == ("2026", "12")


def test_resolve_current_term_tolerates_non_string_text() -> None:
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/html"},
        text=None,
    )

    assert term_module.resolve_current_term(FakeClient(response)) is None
