"""Configuration loading tests."""

import json
from argparse import Namespace

import pytest

from cumt_jwxt_cli.config import load_app_config, resolve_config_path
from cumt_jwxt_cli.errors import ConfigError


def _query_args(**overrides: object) -> Namespace:
    values = {
        "config": None,
        "year": None,
        "semester": None,
        "no_interactive": True,
        "save_json": False,
        "save_report": False,
        "output_dir": None,
    }
    values.update(overrides)
    return Namespace(**values)


def _write_config(path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_app_config_reads_required_fields(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"year": "2024", "semester": "12"},
            "notify": {
                "sender_name": "cumt-jwxt-cli",
                "recipients": ["user@example.test"],
            },
        },
    )

    config = load_app_config(_query_args(config=str(config_path)))

    assert config.config_path == config_path.resolve()
    assert config.cumt.username == "student"
    assert config.cumt.password == "secret"
    assert config.query.year == "2024"
    assert config.query.semester == "12"
    assert config.http.timeout_seconds == 30.0
    assert config.grades.detail_concurrency == 3
    assert config.notify.sender_name == "cumt-jwxt-cli"
    assert config.notify.recipients == ("user@example.test",)


def test_load_app_config_cli_overrides_file_values(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"year": "2024", "semester": "12"},
            "output": {"save_json": False, "save_report": False, "output_dir": ""},
        },
    )

    config = load_app_config(
        _query_args(
            config=str(config_path),
            year="2025",
            semester="3",
            save_json=True,
            save_report=True,
            output_dir="reports",
        )
    )

    assert config.query.year == "2025"
    assert config.query.semester == "3"
    assert config.output.save_json is True
    assert config.output.save_report is True
    assert config.output.output_dir == "reports"


def test_load_app_config_env_overrides_sensitive_fields(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "file-user", "password": "file-password"},
            "query": {"year": "2024", "semester": "12"},
            "captcha": {
                "openai_compatible": {
                    "api_key": "file-key",
                    "base_url": "https://example.test/v1",
                    "model": "file-model",
                }
            },
        },
    )
    monkeypatch.setenv("CUMT_JWXT_USERNAME", "env-user")
    monkeypatch.setenv("CUMT_JWXT_PASSWORD", "env-password")
    monkeypatch.setenv("CUMT_JWXT_CAPTCHA_OPENAI_COMPATIBLE_API_KEY", "env-key")

    config = load_app_config(_query_args(config=str(config_path)))

    assert config.cumt.username == "env-user"
    assert config.cumt.password == "env-password"
    assert config.captcha.openai_compatible.api_key == "env-key"


def test_load_app_config_missing_required_field_fails(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(config_path, {"cumt": {"username": "student"}})

    with pytest.raises(ConfigError, match="cumt.password"):
        load_app_config(_query_args(config=str(config_path)))


def test_load_app_config_interactively_creates_missing_config(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    answers = iter(
        [
            "student",
            "secret",
            "2026",
            "3",
            "https://captcha.example.test/v1",
            "captcha-key",
            "captcha-model",
        ]
    )

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    config = load_app_config(
        _query_args(config=str(config_path), no_interactive=False)
    )

    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.cumt.username == "student"
    assert config.cumt.password == "secret"
    assert config.query.year == "2026"
    assert config.query.semester == "3"
    assert config.captcha.openai_compatible.api_key == "captcha-key"
    assert written["cumt"]["username"] == "student"
    assert written["captcha"]["openai_compatible"]["model"] == "captcha-model"


def test_load_app_config_interactively_completes_missing_fields(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": ""},
            "query": {"year": "2026", "semester": "3"},
        },
    )
    answers = iter(["secret", "", "", ""])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    config = load_app_config(
        _query_args(config=str(config_path), no_interactive=False)
    )

    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.cumt.password == "secret"
    assert written["cumt"]["password"] == "secret"
    assert written["query"]["year"] == "2026"


def test_load_app_config_interactive_skips_env_backed_fields(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(config_path, {"query": {"year": "2026", "semester": "3"}})
    answers = iter(["https://captcha.example.test/v1", "captcha-key", "model"])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setenv("CUMT_JWXT_USERNAME", "env-user")
    monkeypatch.setenv("CUMT_JWXT_PASSWORD", "env-password")

    config = load_app_config(
        _query_args(config=str(config_path), no_interactive=False)
    )

    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.cumt.username == "env-user"
    assert config.cumt.password == "env-password"
    assert "cumt" not in written


def test_load_app_config_invalid_json_fails(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text("{", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid JSON"):
        load_app_config(_query_args(config=str(config_path)))


def test_resolve_config_path_prefers_local_config_in_current_directory(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(config_path, {})
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path(None) == config_path.resolve()
