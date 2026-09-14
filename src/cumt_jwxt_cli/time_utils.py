"""Shared helpers for ISO 8601 timestamps and academic-term resolution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

ErrorFactory = Callable[[str], Exception]

# JWXT encodes the autumn semester as 3 and the spring semester as 12.
AUTUMN_SEMESTER = "3"
SPRING_SEMESTER = "12"
# The academic calendar follows Beijing time, which has no daylight saving.
_CHINA_STANDARD_TIME = timezone(timedelta(hours=8))


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""

    return datetime.now(UTC).isoformat()


def resolve_query_scope(now: datetime | None = None) -> tuple[str, str]:
    """Derive the JWXT (year, semester) pair from the current date in China.

    The autumn semester starts in September and runs through January, so January
    still belongs to the academic year that began the previous September. Late
    summer (through August) stays on the previous spring semester, which avoids
    switching to an empty new term before any grades exist.

    The result is a best-effort default: it follows the calendar, not the actual
    school calendar, so callers should still allow explicit year/semester values.
    """

    moment = datetime.now(_CHINA_STANDARD_TIME) if now is None else now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_CHINA_STANDARD_TIME)
    else:
        moment = moment.astimezone(_CHINA_STANDARD_TIME)

    if moment.month >= 9:
        return str(moment.year), AUTUMN_SEMESTER
    if moment.month == 1:
        return str(moment.year - 1), AUTUMN_SEMESTER
    return str(moment.year - 1), SPRING_SEMESTER


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
