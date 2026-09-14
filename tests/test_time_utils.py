"""Shared timestamp helper tests."""

from datetime import UTC, datetime, timedelta

import pytest

from cumt_jwxt_cli.time_utils import (
    AUTUMN_SEMESTER,
    SPRING_SEMESTER,
    normalize_optional_iso_timestamp,
    resolve_query_scope,
    utc_now_iso,
)


def _runtime_error(message: str) -> Exception:
    return RuntimeError(message)


def test_normalize_optional_iso_timestamp_accepts_none_and_preserves_z_suffix() -> None:
    assert (
        normalize_optional_iso_timestamp(
            None,
            field_label="State field queried_at",
            error_factory=_runtime_error,
        )
        is None
    )
    assert (
        normalize_optional_iso_timestamp(
            "2026-05-05T04:00:00Z",
            field_label="State field queried_at",
            error_factory=_runtime_error,
        )
        == "2026-05-05T04:00:00Z"
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (123, "State field queried_at must be a string or null."),
        ("  ", "State field queried_at must not be blank when present."),
        ("not-a-timestamp", "State field queried_at must be an ISO 8601 timestamp."),
    ],
)
def test_normalize_optional_iso_timestamp_rejects_invalid_values(
    value: object,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        normalize_optional_iso_timestamp(
            value,
            field_label="State field queried_at",
            error_factory=_runtime_error,
        )


def test_utc_now_iso_returns_utc_timestamp() -> None:
    parsed = datetime.fromisoformat(utc_now_iso())

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 9, 1, 0, 0), ("2026", AUTUMN_SEMESTER)),
        (datetime(2026, 12, 31, 23, 30), ("2026", AUTUMN_SEMESTER)),
        (datetime(2027, 1, 1, 0, 30), ("2026", AUTUMN_SEMESTER)),
        (datetime(2027, 1, 31, 23, 59), ("2026", AUTUMN_SEMESTER)),
        (datetime(2027, 2, 1, 0, 0), ("2026", SPRING_SEMESTER)),
        (datetime(2027, 7, 31, 23, 59), ("2026", SPRING_SEMESTER)),
        (datetime(2027, 8, 31, 23, 59), ("2026", SPRING_SEMESTER)),
    ],
)
def test_resolve_query_scope_follows_china_calendar_boundaries(
    moment: datetime,
    expected: tuple[str, str],
) -> None:
    assert resolve_query_scope(moment) == expected


def test_resolve_query_scope_converts_aware_time_to_china() -> None:
    # 2026-08-31T17:00Z is already 2026-09-01 in Beijing, so it is the new autumn.
    utc_moment = datetime(2026, 8, 31, 17, 0, tzinfo=UTC)

    assert resolve_query_scope(utc_moment) == ("2026", AUTUMN_SEMESTER)
