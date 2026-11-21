"""Configuration loading tests."""

import json
from argparse import Namespace

import pytest

from cumt_jwxt_cli.config import (
    _read_config_template,
    load_app_config,
    resolve_config_path,
)
from cumt_jwxt_cli.errors import ConfigError


def _query_args(**overrides: object) -> Namespace:
    values = {
        "config": None,
        "year": None,
        "semester": None,
        "no_interactive": True,
        "save_json": False,
        "save_report": False,
        "save_ics": False,
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
            "output": {
                "save_json": False,
                "save_report": False,
                "save_ics": False,
                "output_dir": "",
            },
        },
    )

    config = load_app_config(
        _query_args(
            config=str(config_path),
            year="2025",
            semester="3",
            save_json=True,
            save_report=True,
            save_ics=True,
            output_dir="reports",
        )
    )

    assert config.query.year == "2025"
    assert config.query.semester == "3"
    assert config.output.save_json is True
    assert config.output.save_report is True
    assert config.output.save_ics is True
    assert config.output.output_dir == "reports"


def test_load_app_config_env_overrides_sensitive_fields(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "file-user", "password": "file-password"},
            "query": {"year": "2024", "semester": "12"},
        },
    )
    monkeypatch.setenv("CUMT_JWXT_USERNAME", "env-user")
    monkeypatch.setenv("CUMT_JWXT_PASSWORD", "env-password")

    config = load_app_config(_query_args(config=str(config_path)))

    assert config.cumt.username == "env-user"
    assert config.cumt.password == "env-password"


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
    answers = iter(["student", "secret"])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(
        "cumt_jwxt_cli.config._read_config_template",
        lambda: {"query": {"year": "2026", "semester": "3"}},
    )

    config = load_app_config(_query_args(config=str(config_path), no_interactive=False))

    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert config.cumt.username == "student"
    assert config.cumt.password == "secret"
    assert config.query.year == "2026"
    assert config.query.semester == "3"
    assert written["cumt"]["username"] == "student"


def test_read_config_template_loads_example_config() -> None:
    template = _read_config_template()

    assert template
    assert "query" in template


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
    answers = iter(["secret"])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    config = load_app_config(_query_args(config=str(config_path), no_interactive=False))

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
    answers = iter([])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setenv("CUMT_JWXT_USERNAME", "env-user")
    monkeypatch.setenv("CUMT_JWXT_PASSWORD", "env-password")

    config = load_app_config(_query_args(config=str(config_path), no_interactive=False))

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


def test_resolve_config_path_falls_back_to_repo_root(
    tmp_path,
    monkeypatch,
) -> None:
    """A source checkout's root config should be found when cwd has none."""

    project_root = tmp_path / "proj"
    module_dir = project_root / "src" / "cumt_jwxt_cli"
    module_dir.mkdir(parents=True)
    fake_module = module_dir / "config.py"
    fake_module.write_text("", encoding="utf-8")

    root_config = project_root / "config.json"
    _write_config(
        root_config,
        {"cumt": {"username": "placeholder", "password": "placeholder"}},
    )

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.setattr("cumt_jwxt_cli.config.__file__", str(fake_module))
    monkeypatch.chdir(elsewhere)

    assert resolve_config_path(None) == root_config.resolve()


def test_load_app_config_auto_defers_scope_resolution(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"auto": True},
        },
    )

    def fail_resolve() -> tuple[str, str]:
        raise AssertionError("config loading must not derive the scope")

    monkeypatch.setattr("cumt_jwxt_cli.time_utils.resolve_query_scope", fail_resolve)

    config = load_app_config(_query_args(config=str(config_path)))

    assert config.query.year == ""
    assert config.query.semester == ""
    assert config.query.auto is True


def test_load_app_config_explicit_scope_wins_over_auto(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"auto": True, "year": "2024", "semester": "12"},
        },
    )

    config = load_app_config(_query_args(config=str(config_path)))

    assert config.query.year == "2024"
    assert config.query.semester == "12"
    assert config.query.auto is True


def test_load_app_config_cli_overrides_auto_derivation(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"auto": True},
        },
    )

    config = load_app_config(
        _query_args(config=str(config_path), year="2025", semester="3")
    )

    assert config.query.year == "2025"
    assert config.query.semester == "3"


def test_load_app_config_missing_scope_without_auto_fails(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {"cumt": {"username": "student", "password": "secret"}, "query": {}},
    )

    with pytest.raises(ConfigError, match="query.year"):
        load_app_config(_query_args(config=str(config_path)))


def test_load_app_config_partial_scope_with_auto_fails(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"auto": True, "year": "2024"},
        },
    )

    with pytest.raises(ConfigError, match="query.semester"):
        load_app_config(_query_args(config=str(config_path)))


def test_load_app_config_rejects_non_boolean_auto(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(
        config_path,
        {
            "cumt": {"username": "student", "password": "secret"},
            "query": {"auto": "yes"},
        },
    )

    with pytest.raises(ConfigError, match="query.auto"):
        load_app_config(_query_args(config=str(config_path)))


def test_load_app_config_interactive_skips_scope_prompts_with_auto(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.local.json"
    _write_config(config_path, {"query": {"auto": True}})
    answers = iter(["student", "secret"])

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    config = load_app_config(_query_args(config=str(config_path), no_interactive=False))

    assert config.cumt.username == "student"
    assert config.cumt.password == "secret"
    assert config.query.year == ""
    assert config.query.semester == ""
    assert config.query.auto is True
