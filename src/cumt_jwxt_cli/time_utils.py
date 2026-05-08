"""Shared helpers for ISO 8601 timestamps."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

ErrorFactory = Callable[[str], Exception]


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""

    return datetime.now(UTC).isoformat()


def normalize_optional_iso_timestamp(
    value: object,
    *,
    field_label: str,
    error_factory: ErrorFactory,
) -> str | None:
    """Validate and normalize an optional ISO 8601 timestamp string."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise error_factory(f"{field_label} must be a string or null.")

    stripped = value.strip()
    if not stripped:
        raise error_factory(f"{field_label} must not be blank when present.")

    value_to_parse = (
        stripped.removesuffix("Z") + "+00:00" if stripped.endswith("Z") else stripped
    )
    try:
        datetime.fromisoformat(value_to_parse)
    except ValueError as exc:
        raise error_factory(f"{field_label} must be an ISO 8601 timestamp.") from exc
    return stripped
