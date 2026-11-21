"""Resolve the current academic term from JWXT.

JWXT has no dedicated "current term" endpoint. The free-classroom page carries
the active ``xnm``/``xqm`` values as hidden inputs, so we read them from there
after login. This is a best-effort lookup: structural problems return ``None``
and let callers fall back to the calendar.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from cumt_jwxt_cli.client.http import ensure_authenticated_response

TERM_PAGE_PATH = "/cdjy/cdjy_cxKxcdlb.html"
TERM_PAGE_PARAMS = {"gnmkdm": "N2155", "layout": "default"}

# JWXT encodes autumn as 3, spring as 12, and short summer as 16.
VALID_SEMESTERS = frozenset({"3", "12", "16"})


def resolve_current_term(client: object) -> tuple[str, str] | None:
    """Return the JWXT ``(year, semester)`` pair, or ``None`` if unavailable.

    A dead session raises :class:`SessionExpiredError` so the orchestrator can
    log in again. Any other malformed page is treated as "unknown" and returns
    ``None``.
    """

    response = client.get(TERM_PAGE_PATH, params=dict(TERM_PAGE_PARAMS))
    # The page legitimately returns HTML, so only redirect/901 markers indicate
    # an expired session here.
    ensure_authenticated_response(
        response,
        "current term",
        html_is_session_expiry=False,
    )

    page_html = getattr(response, "text", "")
    if not isinstance(page_html, str) or not page_html.strip():
        return None

    soup = BeautifulSoup(page_html, "html.parser")
    year = _input_value(soup, "xnm")
    semester = _input_value(soup, "xqm")

    if year is None or semester is None:
        return None
    if len(year) != 4 or not year.isdigit():
        return None
    if semester not in VALID_SEMESTERS:
        return None
    return year, semester


def _input_value(soup: BeautifulSoup, element_id: str) -> str | None:
    tag = soup.find(id=element_id)
    if tag is None:
        return None
    value = tag.get("value")
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
