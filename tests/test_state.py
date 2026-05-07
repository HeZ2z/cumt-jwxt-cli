"""Runtime state storage tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    GradesConfig,
    GradeSnapshotEntry,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
    RuntimeState,
)
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state

_ALLOWED_STATE_KEYS = {
    "schema_version",
    "session_cookies",
    "session_updated_at",
    "last_grade_snapshot",
    "last_successful_query_at",
    "last_notified_at",
}


def _app_config(config_path: Path) -> AppConfig:
    return AppConfig(
        config_path=config_path,
        cumt=CUMTConfig(username="student", password="secret"),
        query=QueryConfig(year="2024", semester="12"),
        http=HTTPConfig(
            timeout_seconds=30.0,
            retry_attempts=2,
            retry_backoff_seconds=1.5,
        ),
        grades=GradesConfig(include_details_on_change=True, detail_concurrency=3),
        captcha=CaptchaConfig(
            provider="openai_compatible",
            manual_timeout_seconds=60,
            openai_compatible=OpenAICompatibleConfig(base_url="", api_key="", model=""),
        ),
        notify=NotifyConfig(
            enabled=False,
            smtp_host="",
            smtp_port=465,
            username="",
            password="",
            sender="",
            recipients=(),
        ),
        logging=LoggingConfig(retention_days=14),
        output=OutputConfig(save_json=False, save_report=False, output_dir=""),
    )


def test_load_runtime_state_returns_default_when_missing(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")

    assert load_runtime_state(config) == RuntimeState(
        schema_version=2,
        session_cookies={},
        session_updated_at=None,
        last_grade_snapshot=(),
        last_successful_query_at=None,
        last_notified_at=None,
    )


def test_runtime_state_round_trip(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=2,
        session_cookies={"JSESSIONID": "session-id", "route": "route-id"},
        session_updated_at="2026-05-05T11:59:00+08:00",
        last_grade_snapshot=(
            GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
        ),
        last_successful_query_at="2026-05-05T12:00:00+08:00",
        last_notified_at=None,
    )

    save_runtime_state(config, state)

    assert load_runtime_state(config) == state


def test_load_runtime_state_rejects_invalid_json(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text("{", encoding="utf-8")

    with pytest.raises(StateError, match="not valid JSON"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_structure(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps({"schema_version": 1, "unexpected": "value"}),
        encoding="utf-8",
    )

    with pytest.raises(StateError):
        load_runtime_state(config)


def test_load_runtime_state_rejects_older_schema_version(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 0,
                "session_cookies": {},
                "session_updated_at": None,
                "last_grade_snapshot": [],
                "last_successful_query_at": None,
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="Unsupported state schema_version"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_newer_schema_version(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "session_cookies": {},
                "session_updated_at": None,
                "last_grade_snapshot": [],
                "last_successful_query_at": None,
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="Unsupported state schema_version"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_timestamp(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_cookies": {},
                "session_updated_at": None,
                "last_grade_snapshot": [],
                "last_successful_query_at": "not-a-timestamp",
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="ISO 8601 timestamp"):
        load_runtime_state(config)


def test_save_runtime_state_uses_strict_top_level_schema(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=2,
        session_cookies={"JSESSIONID": "session-id", "route": "route-id"},
        session_updated_at="2026-05-05T11:59:00+08:00",
        last_grade_snapshot=(
            GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
        ),
        last_successful_query_at="2026-05-05T12:00:00+08:00",
        last_notified_at="2026-05-05T12:05:00+08:00",
    )

    save_runtime_state(config, state)

    serialized = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(serialized) == _ALLOWED_STATE_KEYS
    assert serialized["schema_version"] == 2
    assert serialized["session_cookies"] == {
        "JSESSIONID": "session-id",
        "route": "route-id",
    }
    assert serialized["session_updated_at"] == "2026-05-05T11:59:00+08:00"
    assert serialized["last_grade_snapshot"] == [
        {"course_code": "A001", "course_name": "高等数学", "score": "95"}
    ]
    assert "username" not in serialized
    assert "password" not in serialized
    assert "username" not in json.dumps(serialized)
    assert "password" not in json.dumps(serialized)


def test_save_runtime_state_rejects_unsupported_schema_version(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=3,
        session_cookies={},
        session_updated_at=None,
        last_grade_snapshot=(),
        last_successful_query_at=None,
        last_notified_at=None,
    )

    with pytest.raises(StateError, match="Unsupported state schema_version"):
        save_runtime_state(config, state)


def test_save_runtime_state_rejects_invalid_timestamp(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=2,
        session_cookies={},
        session_updated_at=None,
        last_grade_snapshot=(),
        last_successful_query_at="  ",
        last_notified_at=None,
    )

    with pytest.raises(StateError, match="must not be blank"):
        save_runtime_state(config, state)


def test_runtime_state_round_trip_preserves_utc_z_suffix(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=2,
        session_cookies={},
        session_updated_at=None,
        last_grade_snapshot=(),
        last_successful_query_at="2026-05-05T04:00:00Z",
        last_notified_at="2026-05-05T04:05:00Z",
    )

    save_runtime_state(config, state)

    assert load_runtime_state(config) == state


def test_load_runtime_state_migrates_schema_v1_without_session(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "last_grade_snapshot": [
                    {"course_code": "A001", "course_name": "高等数学", "score": "95"}
                ],
                "last_successful_query_at": "2026-05-05T12:00:00+08:00",
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    assert load_runtime_state(config) == RuntimeState(
        schema_version=2,
        session_cookies={},
        session_updated_at=None,
        last_grade_snapshot=(
            GradeSnapshotEntry(course_code="A001", course_name="高等数学", score="95"),
        ),
        last_successful_query_at="2026-05-05T12:00:00+08:00",
        last_notified_at=None,
    )


def test_load_runtime_state_rejects_invalid_session_cookie_value(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_cookies": {"JSESSIONID": 123},
                "session_updated_at": None,
                "last_grade_snapshot": [],
                "last_successful_query_at": None,
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="cookie values"):
        load_runtime_state(config)
