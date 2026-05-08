"""Shared timestamp helper tests."""

from datetime import datetime, timedelta

import pytest

from cumt_jwxt_cli.time_utils import normalize_optional_iso_timestamp, utc_now_iso


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
