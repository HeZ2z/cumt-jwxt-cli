"""Paginated JWXT list fetching helpers."""

from __future__ import annotations

from collections.abc import Mapping

from cumt_jwxt_cli.client.http import ensure_authenticated_response
from cumt_jwxt_cli.errors import ParseError, QueryError


def fetch_all_items(
    client: object,
    path: str,
    *,
    params: Mapping[str, str] | None = None,
    data: Mapping[str, str],
    headers: Mapping[str, str] | None = None,
    label: str,
    page_size: int = 100,
    max_pages: int = 10,
) -> list[object]:
    """Fetch every item from a paged JWXT list endpoint.

    The JWXT list APIs silently truncate at ``queryModel.showCount`` items, so a
    single request could store an incomplete snapshot and hide grade changes.
    This walks pages until a short/empty page, an explicit ``totalResult``, or a
    repeated page is seen, and refuses to return a possibly truncated list.
    """

    items: list[object] = []
    previous_page: list[object] | None = None

    for page_number in range(1, max_pages + 1):
        page_data = {
            **data,
            "queryModel.showCount": str(page_size),
            "queryModel.currentPage": str(page_number),
        }
        payload = _fetch_page(
            client,
            path,
            params=params,
            data=page_data,
            headers=headers,
            label=label,
        )
        page_items = _extract_items(payload, label)
        total = _total_result(payload)

        if not page_items:
            if total is not None and total > len(items):
                raise _ended_early_error(label, len(items), total)
            break

        # Some JWXT deployments ignore paging and return the same page again;
        # stop without appending duplicates.
        if previous_page is not None and page_items == previous_page:
            if total is not None and total > len(items):
                raise _ended_early_error(label, len(items), total)
            break

        items.extend(page_items)

        if total is not None and total <= len(items):
            break
        if len(page_items) < page_size:
            if total is not None and total > len(items):
                # The server may cap the page size below what we requested;
                # keep paging until totalResult is reached.
                previous_page = page_items
                continue
            break

        previous_page = page_items
    else:
        raise QueryError(
            f"JWXT {label} response exceeded {max_pages} pages; "
            "refusing to store a truncated snapshot."
        )

    return items


def _total_result(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    total_result = payload.get("totalResult")
    if isinstance(total_result, int) and not isinstance(total_result, bool):
        return total_result
    return None


def _ended_early_error(label: str, count: int, total: int) -> QueryError:
    return QueryError(f"JWXT {label} response ended early at {count} of {total} items.")


def _fetch_page(
    client: object,
    path: str,
    *,
    params: Mapping[str, str] | None,
    data: Mapping[str, str],
    headers: Mapping[str, str] | None,
    label: str,
) -> object:
    kwargs: dict[str, object] = {"data": data}
    if params is not None:
        kwargs["params"] = params
    if headers is not None:
        kwargs["headers"] = headers
    try:
        response = client.post(path, **kwargs)
        ensure_authenticated_response(response, label)
        return response.json()
    except ValueError as exc:
        raise QueryError(f"JWXT {label} response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _extract_items(payload: object, label: str) -> list[object]:
    if not isinstance(payload, dict):
        raise ParseError(f"{label.capitalize()} payload must be a JSON object.")
    if "items" not in payload:
        raise ParseError(f"{label.capitalize()} payload must contain items.")

    items = payload["items"]
    if not isinstance(items, list):
        raise ParseError(f"{label.capitalize()} payload items must be a list.")
    return items
