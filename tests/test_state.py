"""Runtime state storage tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    ExamScopeState,
    ExamSnapshotEntry,
    GradeQueryScope,
    GradesConfig,
    GradeSnapshotEntry,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    PerScopeState,
    QueryConfig,
    RuntimeState,
)
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state

_ALLOWED_STATE_KEYS = {
    "schema_version",
    "session_cookies",
    "session_updated_at",
    "grade_queries",
    "exam_queries",
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
        output=OutputConfig(
            save_json=False, save_report=False, save_ics=False, output_dir=""
        ),
    )


def _scope(year: str = "2024", semester: str = "12") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _grade_entry(course_code: str, course_name: str, score: str) -> GradeSnapshotEntry:
    return GradeSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        score=score,
    )


def _exam_entry(
    course_code: str,
    course_name: str,
    **overrides: str | None,
) -> ExamSnapshotEntry:
    return ExamSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        exam_time=overrides.get("exam_time"),
        location=overrides.get("location"),
        campus=overrides.get("campus"),
        exam_name=overrides.get("exam_name"),
        exam_method=overrides.get("exam_method"),
    )


def _per_scope(
    snapshot: tuple[GradeSnapshotEntry, ...],
    *,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> PerScopeState:
    return PerScopeState(
        snapshot=snapshot,
        last_successful_query_at=last_successful_query_at,
        last_notified_at=last_notified_at,
    )


def _exam_scope(
    snapshot: tuple[ExamSnapshotEntry, ...],
    *,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> ExamScopeState:
    return ExamScopeState(
        snapshot=snapshot,
        last_successful_query_at=last_successful_query_at,
        last_notified_at=last_notified_at,
    )


def test_load_runtime_state_returns_default_when_missing(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")

    assert load_runtime_state(config) == RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
    )


def test_runtime_state_round_trip_with_multiple_scopes(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={"JSESSIONID": "session-id", "route": "route-id"},
        session_updated_at="2026-05-05T11:59:00+08:00",
        grade_queries={
            _scope("2025", "3"): _per_scope(
                (_grade_entry("A001", "高等数学", "95"),),
                last_successful_query_at="2026-05-05T12:00:00+08:00",
                last_notified_at=None,
            ),
            _scope("2025", "12"): _per_scope(
                (_grade_entry("B002", "大学英语", "88"),),
                last_successful_query_at="2026-05-06T12:00:00+08:00",
                last_notified_at="2026-05-06T12:05:00+08:00",
            ),
        },
        exam_queries={
            _scope("2025", "3"): _exam_scope(
                (_exam_entry("E001", "高数考试", exam_time="2026-06-01(08:00)"),),
                last_successful_query_at="2026-05-05T12:00:00+08:00",
            ),
        },
    )

    save_runtime_state(config, state)

    assert load_runtime_state(config) == state


def test_runtime_state_round_trip_with_empty_grade_queries(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
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
        json.dumps({"schema_version": 4, "unexpected": "value"}),
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
                "grade_queries": {},
                "exam_queries": {},
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
                "schema_version": 5,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {},
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="Unsupported state schema_version"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_v4_scope_key(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {"": {}},
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="scope keys"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_v4_grade_queries(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": [],
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="grade_queries must be an object"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_v4_per_scope_state(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {
                    "2025-3": {
                        "last_successful_query_at": None,
                        "last_notified_at": None,
                    }
                },
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="supported keys"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_v4_snapshot_entry(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {
                    "2025-3": {
                        "snapshot": [{"course_code": "A001"}],
                        "last_successful_query_at": None,
                        "last_notified_at": None,
                    }
                },
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="snapshot entry"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_v4_timestamp(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {
                    "2025-3": {
                        "snapshot": [],
                        "last_successful_query_at": "not-a-timestamp",
                        "last_notified_at": None,
                    }
                },
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="ISO 8601 timestamp"):
        load_runtime_state(config)


def test_save_runtime_state_uses_strict_top_level_schema(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={"JSESSIONID": "session-id", "route": "route-id"},
        session_updated_at="2026-05-05T11:59:00+08:00",
        grade_queries={
            _scope("2025", "3"): _per_scope(
                (_grade_entry("A001", "高等数学", "95"),),
                last_successful_query_at="2026-05-05T12:00:00+08:00",
                last_notified_at="2026-05-05T12:05:00+08:00",
            )
        },
        exam_queries={},
    )

    save_runtime_state(config, state)

    serialized = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(serialized) == _ALLOWED_STATE_KEYS
    assert serialized["schema_version"] == 4
    assert serialized["session_cookies"] == {
        "JSESSIONID": "session-id",
        "route": "route-id",
    }
    assert serialized["session_updated_at"] == "2026-05-05T11:59:00+08:00"
    assert serialized["grade_queries"] == {
        "2025-3": {
            "snapshot": [
                {"course_code": "A001", "course_name": "高等数学", "score": "95"}
            ],
            "last_successful_query_at": "2026-05-05T12:00:00+08:00",
            "last_notified_at": "2026-05-05T12:05:00+08:00",
        }
    }
    assert serialized["exam_queries"] == {}
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
        grade_queries={},
        exam_queries={},
    )

    with pytest.raises(StateError, match="Unsupported state schema_version"):
        save_runtime_state(config, state)


def test_save_runtime_state_rejects_invalid_timestamp(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={
            _scope(): _per_scope(
                (),
                last_successful_query_at="  ",
                last_notified_at=None,
            )
        },
        exam_queries={},
    )

    with pytest.raises(StateError, match="must not be blank"):
        save_runtime_state(config, state)


def test_runtime_state_round_trip_preserves_utc_z_suffix(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={
            _scope(): _per_scope(
                (),
                last_successful_query_at="2026-05-05T04:00:00Z",
                last_notified_at="2026-05-05T04:05:00Z",
            )
        },
        exam_queries={},
    )

    save_runtime_state(config, state)

    assert load_runtime_state(config) == state


def test_load_runtime_state_resets_schema_v1_to_empty_v4(tmp_path) -> None:
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

    expected = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={},
    )
    assert load_runtime_state(config) == expected
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8")) == {
        "schema_version": 4,
        "session_cookies": {},
        "session_updated_at": None,
        "grade_queries": {},
        "exam_queries": {},
    }


def test_load_runtime_state_migrates_schema_v2_to_v4_preserving_cookies(
    tmp_path,
) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_cookies": {"JSESSIONID": "session-id"},
                "session_updated_at": "2026-05-05T11:59:00+08:00",
                "last_grade_snapshot": [
                    {"course_code": "A001", "course_name": "高等数学", "score": "95"}
                ],
                "last_successful_query_at": "not-a-scope-safe-timestamp",
                "last_notified_at": None,
            }
        ),
        encoding="utf-8",
    )

    state = load_runtime_state(config)
    assert state.schema_version == 4
    assert state.session_cookies == {"JSESSIONID": "session-id"}
    assert state.session_updated_at == "2026-05-05T11:59:00+08:00"
    assert state.grade_queries == {}
    assert state.exam_queries == {}

    serialized = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert serialized["schema_version"] == 4
    assert serialized["session_cookies"] == {"JSESSIONID": "session-id"}
    assert serialized["session_updated_at"] == "2026-05-05T11:59:00+08:00"
    assert serialized["grade_queries"] == {}
    assert serialized["exam_queries"] == {}


def test_load_runtime_state_rejects_invalid_session_cookie_value(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {"JSESSIONID": 123},
                "session_updated_at": None,
                "grade_queries": {},
                "exam_queries": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="cookie values"):
        load_runtime_state(config)


def test_runtime_state_round_trip_with_exam_queries(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={
            _scope("2025", "3"): _exam_scope(
                (
                    _exam_entry(
                        "E001",
                        "高数考试",
                        exam_time="2026-06-01(08:00-10:00)",
                        location="博1-A101",
                        campus="南湖校区",
                    ),
                ),
                last_successful_query_at="2026-05-05T12:00:00+08:00",
                last_notified_at="2026-05-05T12:05:00+08:00",
            ),
            _scope("2025", "12"): _exam_scope(
                (_exam_entry("E002", "英语考试"),),
            ),
        },
    )

    save_runtime_state(config, state)
    assert load_runtime_state(config) == state


def test_load_runtime_state_migrates_v3_to_v4_preserving_grade_and_exam_queries(
    tmp_path,
) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "session_cookies": {"JSESSIONID": "existing"},
                "session_updated_at": "2026-05-05T12:00:00+08:00",
                "grade_queries": {
                    "2025-3": {
                        "snapshot": [
                            {
                                "course_code": "A001",
                                "course_name": "高等数学",
                                "score": "95",
                            }
                        ],
                        "last_successful_query_at": "2026-05-05T12:00:00+08:00",
                        "last_notified_at": None,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    state = load_runtime_state(config)
    assert state.schema_version == 4
    assert state.session_cookies == {"JSESSIONID": "existing"}
    assert len(state.grade_queries) == 1
    assert state.exam_queries == {}

    serialized = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert serialized["schema_version"] == 4
    assert set(serialized["grade_queries"]) == {"2025-3"}
    assert serialized["exam_queries"] == {}


def test_load_runtime_state_rejects_invalid_exam_queries_type(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {},
                "exam_queries": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="exam_queries must be an object"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_exam_snapshot_entry(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {},
                "exam_queries": {
                    "2025-3": {
                        "snapshot": [{"course_code": "E001"}],
                        "last_successful_query_at": None,
                        "last_notified_at": None,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="exam snapshot entry"):
        load_runtime_state(config)


def test_load_runtime_state_rejects_invalid_exam_scope_state(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "session_cookies": {},
                "session_updated_at": None,
                "grade_queries": {},
                "exam_queries": {
                    "2025-3": {
                        "snapshot": [],
                        "last_successful_query_at": None,
                        "last_notified_at": None,
                        "unexpected_key": "value",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="supported keys"):
        load_runtime_state(config)


def test_save_runtime_state_includes_exam_queries_in_output(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    state = RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={},
        exam_queries={
            _scope("2025", "3"): _exam_scope(
                (_exam_entry("E001", "高数考试"),),
                last_successful_query_at="2026-05-05T12:00:00+08:00",
            ),
        },
    )

    save_runtime_state(config, state)

    serialized = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "exam_queries" in serialized
    assert serialized["exam_queries"] == {
        "2025-3": {
            "snapshot": [
                {
                    "course_code": "E001",
                    "course_name": "高数考试",
                    "exam_time": None,
                    "location": None,
                    "campus": None,
                    "exam_name": None,
                    "exam_method": None,
                }
            ],
            "last_successful_query_at": "2026-05-05T12:00:00+08:00",
            "last_notified_at": None,
        }
    }
