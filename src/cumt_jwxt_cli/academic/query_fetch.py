"""Transport and parsing helpers for academic status queries."""

from __future__ import annotations

import html as html_module
import logging
import re

from bs4 import BeautifulSoup

from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import (
    AcademicOverview,
    AcademicSummaryResult,
    AppConfig,
    CoursePropertyStat,
    PlanRequirementNode,
)

ACADEMIC_PAGE_PATH = "/xsxy/xsxyqk_cxXsxyqkIndex.html"
# gnmkdm is mandatory: the status page returns HTTP 500 without it.
ACADEMIC_PAGE_PARAMS = {
    "echarts": "1",
    "gnmkdm": "N105515",
    "layout": "default",
}
PROPERTY_GPA_PATH = "/xsxy/xsxyqk_cxKczxAllIndex.html"
PROPERTY_WEIGHTED_PATH = "/xsxy/xsxyqk_cxKczxAllJqxfIndex.html"

_LOGGER = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_LI_TAG_PATTERN = re.compile(r"<li\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_NAME_PATTERN = re.compile(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9（）()·\-]*")
_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_NODE_ID_PATTERN = re.compile(r"id\s*=\s*['\"]p([0-9A-Za-z]+)['\"]", re.IGNORECASE)


def query_academic_summary(
    config: AppConfig,
    client: object,
) -> AcademicSummaryResult:
    """Fetch the cumulative academic page and its supporting statistics.

    ``config.query`` is intentionally ignored: academic status is cumulative
    and is not filtered by academic year or semester.
    """

    page_html = _fetch_page(client)
    overview, plan_nodes, xh_id = parse_academic_page(page_html)
    property_stats = _query_property_stats(client, xh_id)
    return AcademicSummaryResult(
        overview=overview,
        plan_nodes=plan_nodes,
        property_stats=property_stats,
    )


def is_academic_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    return isinstance(exc, SessionExpiredError)


def parse_academic_page(
    page_html: object,
) -> tuple[AcademicOverview, tuple[PlanRequirementNode, ...], str | None]:
    """Parse the overview text, plan requirement tree, and hidden student id."""

    if not isinstance(page_html, str) or not page_html.strip():
        raise ParseError("Academic status page is empty.")

    soup = BeautifulSoup(page_html, "html.parser")
    alert_box = soup.find(id="alertBox")
    if alert_box is None:
        raise ParseError("Academic status page is missing the alertBox overview.")

    overview = parse_academic_overview(alert_box.get_text(" ", strip=True))
    plan_nodes = parse_plan_nodes(page_html)
    return overview, plan_nodes, _extract_xh_id(soup)


def parse_academic_overview(text: str) -> AcademicOverview:
    """Parse the human-readable overview text, tolerating punctuation changes."""

    normalized = _normalize_text(text)
    out_of_plan_index = normalized.find("计划外")
    plan_start = normalized.find("计划课程")
    if plan_start == -1:
        plan_start = normalized.find("计划")

    if out_of_plan_index != -1 and plan_start != -1:
        plan_section = normalized[plan_start:out_of_plan_index]
    elif plan_start != -1:
        plan_section = normalized[plan_start:]
    else:
        plan_section = normalized

    out_section = normalized[out_of_plan_index:] if out_of_plan_index != -1 else ""

    return AcademicOverview(
        snapshot_at=_extract_snapshot_time(normalized),
        gpa_all=_extract_decimal(
            normalized,
            r"(?:全部|所有|当前所有)?\s*课程\s*(?:平均学分绩点)?"
            r"\s*[\(（]?\s*(?:GPA|绩点)\s*[\)）]?",
        ),
        gpa_degree=_extract_decimal(
            normalized,
            r"(?:当前)?\s*学位课\s*(?:平均学分绩点)?"
            r"\s*[\(（]?\s*(?:GPA|绩点)\s*[\)）]?",
        ),
        plan_total=_extract_count(plan_section, r"总(?:课程|门数|数)?"),
        plan_passed=_extract_count(plan_section, r"(?<!未)通过"),
        plan_failed=_extract_count(plan_section, r"未通过"),
        plan_unlearned=_extract_count(plan_section, r"未修"),
        plan_in_progress=_extract_count(plan_section, r"在读"),
        out_of_plan_passed=_extract_count(out_section, r"(?<!未)通过"),
        out_of_plan_failed=_extract_count(out_section, r"未通过"),
    )


def parse_plan_nodes(page_html: str) -> tuple[PlanRequirementNode, ...]:
    """Parse the inline-JS training plan tree in document order.

    The tree is not valid JSON and attribute order differs between JWXT
    deployments, so nodes are read from ``<li>`` attribute blocks plus the
    following markup/JS string until the next sibling ``<li>``.
    """

    matches = list(_LI_TAG_PATTERN.finditer(page_html))
    nodes: list[PlanRequirementNode] = []
    seen: set[str] = set()

    for index, match in enumerate(matches):
        attrs = match.group(1)
        block_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(page_html)
        )
        block = page_html[match.end() : block_end]
        combined = f"{attrs} {block}"

        # The node id lives on the inner title div on real JWXT pages, while
        # some deployments put it on the <li>; look at both.
        node_id = _attribute_value(combined, "xfyqjd_id")
        if not node_id:
            continue
        if node_id in seen:
            continue
        seen.add(node_id)

        marker = _NODE_ID_PATTERN.search(combined)
        tail = combined[marker.end() :] if marker is not None else combined
        name = _extract_node_name(tail, block)

        parent_id = _attribute_value(attrs, "fxfyqjd_id") or _attribute_value(
            combined, "fxfyqjd_id"
        )
        if parent_id in {node_id, "0", "null", "None"}:
            parent_id = None

        nodes.append(
            PlanRequirementNode(
                node_id=node_id,
                name=name,
                parent_id=parent_id,
                required_credits=_credit_value(combined, "yqzdxf"),
                earned_credits=_credit_value(combined, "yxxf"),
                is_passed=_passed_value(_attribute_value(combined, "sftg")),
            )
        )

    return tuple(nodes)


def _fetch_page(client: object) -> str:
    try:
        response = client.get(ACADEMIC_PAGE_PATH, params=dict(ACADEMIC_PAGE_PARAMS))
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc

    status_code = getattr(response, "status_code", None)
    # The status page is server-rendered HTML, so a text/html payload is expected;
    # only redirects and HTTP 901 indicate an expired session here.
    if status_code == 901 or status_code in _REDIRECT_STATUSES:
        raise SessionExpiredError(
            f"JWXT academic status request failed with HTTP {status_code}."
        )

    page_html = getattr(response, "text", None)
    if not isinstance(page_html, str) or not page_html.strip():
        raise QueryError("JWXT academic status response is empty.")
    return page_html


def _query_property_stats(
    client: object, xh_id: str | None
) -> tuple[CoursePropertyStat, ...]:
    if not xh_id:
        _LOGGER.warning(
            "Skipping academic property statistics: student id was not found."
        )
        return ()

    try:
        gpa_items = _fetch_property_items(client, PROPERTY_GPA_PATH, xh_id)
        weighted_items = _fetch_property_items(client, PROPERTY_WEIGHTED_PATH, xh_id)
    except SessionExpiredError:
        # Still allow the session orchestrator to re-login once.
        raise
    except (QueryError, ParseError) as exc:
        _LOGGER.warning(
            "Skipping academic property statistics after query or parse failure.",
            exc_info=exc,
        )
        return ()

    return _merge_property_stats(gpa_items, weighted_items)


def _fetch_property_items(client: object, path: str, xh_id: str) -> list[object]:
    try:
        response = client.get(path, params={"doType": "query", "xh_id": xh_id})
        ensure_authenticated_response(response, "academic property statistics")
        payload = response.json()
    except ValueError as exc:
        raise ParseError(
            "JWXT academic property statistics response is not valid JSON."
        ) from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc

    return parse_property_items(payload)


def parse_property_items(payload: object) -> list[object]:
    """Validate one property-statistics payload and return its item list."""

    if not isinstance(payload, dict):
        raise ParseError("Academic property statistics payload must be an object.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ParseError("Academic property statistics payload must contain items.")
    return items


def _merge_property_stats(
    gpa_items: list[object], weighted_items: list[object]
) -> tuple[CoursePropertyStat, ...]:
    merged: dict[str, dict[str, str | None]] = {}
    order: list[str] = []

    for item in gpa_items:
        entry = _property_entry(merged, order, item)
        if entry is not None:
            entry["gpa"] = _item_text(item, "gpa")
            entry["property_name"] = entry["property_name"] or _item_text(
                item, "kcxzmc"
            )
            entry["earned_credits"] = entry["earned_credits"] or _item_text(
                item, "hdxf"
            )

    for item in weighted_items:
        entry = _property_entry(merged, order, item)
        if entry is not None:
            entry["weighted_average"] = _item_text(item, "jqpjf")
            entry["property_name"] = entry["property_name"] or _item_text(
                item, "kcxzmc"
            )
            entry["earned_credits"] = entry["earned_credits"] or _item_text(
                item, "hdxf"
            )

    return tuple(
        CoursePropertyStat(
            property_code=key or None,
            property_name=merged[key]["property_name"],
            gpa=merged[key]["gpa"],
            weighted_average=merged[key]["weighted_average"],
            earned_credits=merged[key]["earned_credits"],
        )
        for key in order
    )


def _property_entry(
    merged: dict[str, dict[str, str | None]],
    order: list[str],
    item: object,
) -> dict[str, str | None] | None:
    if not isinstance(item, dict):
        return None
    code = _item_text(item, "kcxzdm")
    if not code:
        return None
    if code not in merged:
        merged[code] = {
            "property_name": None,
            "gpa": None,
            "weighted_average": None,
            "earned_credits": None,
        }
        order.append(code)
    return merged[code]


def _extract_xh_id(soup: BeautifulSoup) -> str | None:
    tag = soup.find(id="xh_id")
    if tag is None:
        return None
    value = tag.get("value")
    if value is None:
        value = tag.get_text(strip=True)
    text = str(value).strip()
    return text or None


def _normalize_text(text: str) -> str:
    normalized = html_module.unescape(text).replace("\u3000", " ")
    for source, target in (
        ("：", ":"),
        ("，", ","),
        ("（", "("),
        ("）", ")"),
        ("／", "/"),
        ("\xa0", " "),
    ):
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_snapshot_time(text: str) -> str | None:
    match = re.search(
        r"统计时间\s*:?\s*"
        r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"
        r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        text,
    )
    return match.group(1) if match else None


def _extract_decimal(text: str, label_pattern: str) -> str | None:
    match = re.search(
        rf"{label_pattern}\s*:?\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _extract_count(text: str, label_pattern: str) -> str | None:
    if not text:
        return None
    match = re.search(rf"{label_pattern}\s*:?\s*(\d+)", text)
    return match.group(1) if match else None


def _attribute_value(text: str, name: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s>]+))",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    value = next((group for group in match.groups() if group is not None), "")
    return value.strip() or None


def _credit_value(text: str, name: str) -> str | None:
    value = _attribute_value(text, name)
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned in {"--", "-", "None", "null", "&nbsp;"} or not cleaned:
        return None
    return cleaned


def _passed_value(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "是"}:
        return True
    if normalized in {"0", "false", "否"}:
        return False
    return None


def _extract_node_name(tail: str, block: str) -> str | None:
    # Names sit in inline JS after the p<id> marker. Naive quote pairing breaks
    # because JWXT concatenates strings as `"..." + "..."`, so instead strip JS
    # comments (which contain Chinese labels like 学分) and take the first CJK run.
    without_comments = _COMMENT_PATTERN.sub(" ", tail)
    match = _NAME_PATTERN.search(html_module.unescape(without_comments))
    if match is not None:
        name = _clean_name(match.group(0))
        if name:
            return name

    text = _clean_name(_TAG_PATTERN.sub(" ", block))
    if text and _CJK_PATTERN.search(text):
        return text.split(" ", 1)[0]
    return None


def _clean_name(value: str) -> str | None:
    cleaned = html_module.unescape(value).replace("\xa0", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or None


def _item_text(item: object, key: str) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if text in {"--", "None", "null"}:
        return None
    return text or None
