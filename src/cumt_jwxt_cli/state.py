"""Runtime state storage for grade change detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.models import (
    AppConfig,
    GradeQueryScope,
    GradeSnapshotEntry,
    PerScopeState,
    RuntimeState,
)
from cumt_jwxt_cli.time_utils import normalize_optional_iso_timestamp

_SCHEMA_VERSION = 3
_ALLOWED_KEYS = {
    "schema_version",
    "session_cookies",
    "session_updated_at",
    "grade_queries",
}
_V2_ALLOWED_KEYS = {
    "schema_version",
    "session_cookies",
    "session_updated_at",
    "last_grade_snapshot",
    "last_successful_query_at",
    "last_notified_at",
}
_V1_ALLOWED_KEYS = {
    "schema_version",
    "last_grade_snapshot",
    "last_successful_query_at",
    "last_notified_at",
}


def load_runtime_state(config: AppConfig) -> RuntimeState:
    """Load minimal persisted runtime state for grade change detection."""

    state_path = _state_path(config)
    if not state_path.is_file():
        return _empty_runtime_state()

    try:
        with state_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise StateError(f"State file is not valid JSON: {state_path}") from exc
    except OSError as exc:
        raise StateError(f"Unable to read state file: {state_path}") from exc

    state = _deserialize_runtime_state(payload)
    if payload["schema_version"] in {1, 2}:
        save_runtime_state(config, state)
    return state


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

    if "schema_version" not in payload:
        raise StateError("State file must contain schema_version.")
    schema_version = _validate_schema_version(payload["schema_version"])
    if schema_version == 1:
        allowed_keys = _V1_ALLOWED_KEYS
    elif schema_version == 2:
        allowed_keys = _V2_ALLOWED_KEYS
    else:
        allowed_keys = _ALLOWED_KEYS
    if set(payload) != allowed_keys:
        raise StateError("State file must contain only the supported top-level keys.")

    if schema_version == 1:
        # v1 stored no session_cookies; snapshot is unscoped and cannot be
        # migrated to v3's per-scope structure.
        return _empty_runtime_state()

    if schema_version == 2:
        # v2 session_cookies and session_updated_at are compatible with v3;
        # only the unscoped last_grade_snapshot cannot be migrated.
        return RuntimeState(
            schema_version=_SCHEMA_VERSION,
            session_cookies=_deserialize_session_cookies(payload["session_cookies"]),
            session_updated_at=_normalize_state_timestamp(
                payload.get("session_updated_at"), "session_updated_at"
            ),
            grade_queries={},
        )

    grade_queries_payload = payload["grade_queries"]
    if not isinstance(grade_queries_payload, dict):
        raise StateError("State field grade_queries must be an object.")

    return RuntimeState(
        schema_version=_SCHEMA_VERSION,
        session_cookies=_deserialize_session_cookies(payload["session_cookies"]),
        session_updated_at=_normalize_state_timestamp(
            payload["session_updated_at"], "session_updated_at"
        ),
        grade_queries={
            _deserialize_scope_key(scope_key): _deserialize_per_scope_state(
                scope_payload, scope_key
            )
            for scope_key, scope_payload in grade_queries_payload.items()
        },
    )


def _validate_schema_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateError("State field schema_version must be an integer.")
    if value not in {1, 2, _SCHEMA_VERSION}:
        raise StateError(
            "Unsupported state schema_version "
            f"{value}; expected 1, 2, or {_SCHEMA_VERSION}."
        )
    return value


def _empty_runtime_state() -> RuntimeState:
    return RuntimeState(
        schema_version=_SCHEMA_VERSION,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
    )


def _deserialize_session_cookies(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise StateError("State field session_cookies must be an object.")
    cookies: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise StateError("State session cookie names must be non-blank strings.")
        if not isinstance(value, str):
            raise StateError("State session cookie values must be strings.")
        cookies[key.strip()] = value
    return cookies


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


def _deserialize_scope_key(value: Any) -> GradeQueryScope:
    if not isinstance(value, str) or not value.strip():
        raise StateError("State grade query scope keys must be non-blank strings.")
    parts = value.strip().split("-")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise StateError(
            "State grade query scope keys must use the '<year>-<semester>' format."
        )
    return GradeQueryScope(year=parts[0].strip(), semester=parts[1].strip())


def _serialize_scope_key(scope: GradeQueryScope) -> str:
    year = _required_scope_string(scope.year, "year")
    semester = _required_scope_string(scope.semester, "semester")
    return f"{year}-{semester}"


def _required_scope_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise StateError(f"State grade query scope {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise StateError(f"State grade query scope {field_name} must not be blank.")
    if "-" in stripped:
        raise StateError(f"State grade query scope {field_name} must not contain '-'.")
    return stripped


def _deserialize_per_scope_state(payload: Any, scope_key: str) -> PerScopeState:
    if not isinstance(payload, dict):
        raise StateError(f"State grade query {scope_key} must be an object.")
    if set(payload) != {"snapshot", "last_successful_query_at", "last_notified_at"}:
        raise StateError(
            f"State grade query {scope_key} must contain only supported keys."
        )
    snapshot_payload = payload["snapshot"]
    if not isinstance(snapshot_payload, list):
        raise StateError(f"State grade query {scope_key} snapshot must be a list.")
    return PerScopeState(
        snapshot=tuple(
            _deserialize_snapshot_entry(entry, index)
            for index, entry in enumerate(snapshot_payload)
        ),
        last_successful_query_at=_normalize_state_timestamp(
            payload["last_successful_query_at"],
            f"grade_queries.{scope_key}.last_successful_query_at",
        ),
        last_notified_at=_normalize_state_timestamp(
            payload["last_notified_at"],
            f"grade_queries.{scope_key}.last_notified_at",
        ),
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


def _normalize_state_timestamp(value: Any, field_name: str) -> str | None:
    return normalize_optional_iso_timestamp(
        value,
        field_label=f"State field {field_name}",
        error_factory=StateError,
    )


def _serialize_runtime_state(state: RuntimeState) -> dict[str, object]:
    if state.schema_version != _SCHEMA_VERSION:
        raise StateError(
            "Unsupported state schema_version "
            f"{state.schema_version}; expected {_SCHEMA_VERSION}."
        )
    session_updated_at = _normalize_state_timestamp(
        state.session_updated_at, "session_updated_at"
    )

    return {
        "schema_version": _SCHEMA_VERSION,
        "session_cookies": _deserialize_session_cookies(state.session_cookies),
        "session_updated_at": session_updated_at,
        "grade_queries": {
            _serialize_scope_key(scope): {
                "snapshot": [
                    {
                        "course_code": entry.course_code,
                        "course_name": entry.course_name,
                        "score": entry.score,
                    }
                    for entry in per_scope_state.snapshot
                ],
                "last_successful_query_at": _normalize_state_timestamp(
                    per_scope_state.last_successful_query_at,
                    f"grade_queries.{_serialize_scope_key(scope)}."
                    "last_successful_query_at",
                ),
                "last_notified_at": _normalize_state_timestamp(
                    per_scope_state.last_notified_at,
                    f"grade_queries.{_serialize_scope_key(scope)}.last_notified_at",
                ),
            }
            for scope, per_scope_state in sorted(
                state.grade_queries.items(),
                key=lambda item: _serialize_scope_key(item[0]),
            )
        },
    }
