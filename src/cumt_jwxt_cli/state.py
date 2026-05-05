"""Runtime state storage for grade change detection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.models import AppConfig, GradeSnapshotEntry, RuntimeState

_SCHEMA_VERSION = 1
_ALLOWED_KEYS = {
    "schema_version",
    "last_grade_snapshot",
    "last_successful_query_at",
    "last_notified_at",
}


def load_runtime_state(config: AppConfig) -> RuntimeState:
    """Load minimal persisted runtime state for grade change detection."""

    state_path = _state_path(config)
    if not state_path.is_file():
        return RuntimeState(
            schema_version=_SCHEMA_VERSION,
            last_grade_snapshot=(),
            last_successful_query_at=None,
            last_notified_at=None,
        )

    try:
        with state_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise StateError(f"State file is not valid JSON: {state_path}") from exc
    except OSError as exc:
        raise StateError(f"Unable to read state file: {state_path}") from exc

    return _deserialize_runtime_state(payload)


def save_runtime_state(config: AppConfig, state: RuntimeState) -> None:
    """Persist minimal runtime state using an atomic file replacement."""

    state_path = _state_path(config)
    payload = _serialize_runtime_state(state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_name(f"{state_path.name}.tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temp_path.replace(state_path)
    except OSError as exc:
        raise StateError(f"Unable to write state file: {state_path}") from exc


def _state_path(config: AppConfig) -> Path:
    return config.config_path.parent / "state.json"


def _deserialize_runtime_state(payload: Any) -> RuntimeState:
    if not isinstance(payload, dict):
        raise StateError("State file root must be a JSON object.")
    if set(payload) != _ALLOWED_KEYS:
        raise StateError("State file must contain only the supported top-level keys.")

    schema_version = _validate_schema_version(payload["schema_version"])

    snapshot_payload = payload["last_grade_snapshot"]
    if not isinstance(snapshot_payload, list):
        raise StateError("State field last_grade_snapshot must be a list.")

    return RuntimeState(
        schema_version=schema_version,
        last_grade_snapshot=tuple(
            _deserialize_snapshot_entry(entry, index)
            for index, entry in enumerate(snapshot_payload)
        ),
        last_successful_query_at=_optional_iso_string(
            payload["last_successful_query_at"], "last_successful_query_at"
        ),
        last_notified_at=_optional_iso_string(
            payload["last_notified_at"], "last_notified_at"
        ),
    )


def _validate_schema_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateError("State field schema_version must be an integer.")
    if value != _SCHEMA_VERSION:
        raise StateError(
            f"Unsupported state schema_version {value}; expected {_SCHEMA_VERSION}."
        )
    return value


def _deserialize_snapshot_entry(payload: Any, index: int) -> GradeSnapshotEntry:
    if not isinstance(payload, dict):
        raise StateError(f"State snapshot entry {index} must be an object.")
    if set(payload) != {"course_code", "course_name", "score"}:
        raise StateError(
            f"State snapshot entry {index} must contain only supported snapshot keys."
        )

    return GradeSnapshotEntry(
        course_code=_required_state_string(
            payload["course_code"], "course_code", index
        ),
        course_name=_required_state_string(
            payload["course_name"], "course_name", index
        ),
        score=_required_state_string(payload["score"], "score", index),
    )


def _required_state_string(value: Any, field_name: str, index: int) -> str:
    if not isinstance(value, str):
        raise StateError(
            f"State snapshot entry {index} field {field_name} must be a string."
        )
    stripped = value.strip()
    if not stripped:
        raise StateError(
            f"State snapshot entry {index} field {field_name} must not be blank."
        )
    return stripped


def _optional_iso_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateError(f"State field {field_name} must be a string or null.")
    stripped = value.strip()
    if not stripped:
        raise StateError(f"State field {field_name} must not be blank when present.")

    value_to_parse = (
        stripped.removesuffix("Z") + "+00:00" if stripped.endswith("Z") else stripped
    )
    try:
        datetime.fromisoformat(value_to_parse)
    except ValueError as exc:
        raise StateError(
            f"State field {field_name} must be an ISO 8601 timestamp."
        ) from exc
    return stripped


def _serialize_runtime_state(state: RuntimeState) -> dict[str, object]:
    _validate_schema_version(state.schema_version)
    last_successful_query_at = _optional_iso_string(
        state.last_successful_query_at, "last_successful_query_at"
    )
    last_notified_at = _optional_iso_string(state.last_notified_at, "last_notified_at")

    return {
        "schema_version": _SCHEMA_VERSION,
        "last_grade_snapshot": [
            {
                "course_code": entry.course_code,
                "course_name": entry.course_name,
                "score": entry.score,
            }
            for entry in state.last_grade_snapshot
        ],
        "last_successful_query_at": last_successful_query_at,
        "last_notified_at": last_notified_at,
    }
