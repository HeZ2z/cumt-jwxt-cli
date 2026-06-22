"""Configuration loading for cumt-jwxt-cli."""

from __future__ import annotations

import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

from cumt_jwxt_cli.errors import ConfigError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
)

_ENV_PREFIX = "CUMT_JWXT_"
_DEFAULT_CONFIG_NAMES = ("config.local.json", "config.json")
_PATH_CUMT_USERNAME = ("cumt", "username")
_PATH_CUMT_PASSWORD = ("cumt", "password")
_PATH_QUERY_YEAR = ("query", "year")
_PATH_QUERY_SEMESTER = ("query", "semester")
_PATH_CAPTCHA_PROVIDER = ("captcha", "provider")
_PATH_CAPTCHA_MANUAL_TIMEOUT = ("captcha", "manual_timeout_seconds")
_PATH_CAPTCHA_OPENAI_BASE_URL = ("captcha", "openai_compatible", "base_url")
_PATH_CAPTCHA_OPENAI_API_KEY = ("captcha", "openai_compatible", "api_key")
_PATH_CAPTCHA_OPENAI_MODEL = ("captcha", "openai_compatible", "model")
_PATH_NOTIFY_ENABLED = ("notify", "enabled")
_PATH_NOTIFY_SMTP_HOST = ("notify", "smtp_host")
_PATH_NOTIFY_SMTP_PORT = ("notify", "smtp_port")
_PATH_NOTIFY_USERNAME = ("notify", "username")
_PATH_NOTIFY_PASSWORD = ("notify", "password")
_PATH_NOTIFY_SENDER = ("notify", "sender")
_PATH_NOTIFY_SENDER_NAME = ("notify", "sender_name")
_PATH_NOTIFY_RECIPIENTS = ("notify", "recipients")
_PATH_LOGGING_RETENTION_DAYS = ("logging", "retention_days")
_PATH_OUTPUT_SAVE_JSON = ("output", "save_json")
_PATH_OUTPUT_SAVE_REPORT = ("output", "save_report")
_PATH_OUTPUT_SAVE_ICS = ("output", "save_ics")
_PATH_OUTPUT_DIR = ("output", "output_dir")
_PATH_HTTP_TIMEOUT_SECONDS = ("http", "timeout_seconds")
_PATH_HTTP_RETRY_ATTEMPTS = ("http", "retry_attempts")
_PATH_HTTP_RETRY_BACKOFF_SECONDS = ("http", "retry_backoff_seconds")
_PATH_GRADES_INCLUDE_DETAILS = ("grades", "include_details_on_change")
_PATH_GRADES_DETAIL_CONCURRENCY = ("grades", "detail_concurrency")
_ENV_NAME_BY_PATH = {
    _PATH_CUMT_USERNAME: f"{_ENV_PREFIX}USERNAME",
    _PATH_CUMT_PASSWORD: f"{_ENV_PREFIX}PASSWORD",
    _PATH_CAPTCHA_OPENAI_BASE_URL: (f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_BASE_URL"),
    _PATH_CAPTCHA_OPENAI_API_KEY: f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_API_KEY",
    _PATH_CAPTCHA_OPENAI_MODEL: f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_MODEL",
    _PATH_NOTIFY_SMTP_HOST: f"{_ENV_PREFIX}SMTP_HOST",
    _PATH_NOTIFY_USERNAME: f"{_ENV_PREFIX}SMTP_USERNAME",
    _PATH_NOTIFY_PASSWORD: f"{_ENV_PREFIX}SMTP_PASSWORD",
    _PATH_NOTIFY_SENDER: f"{_ENV_PREFIX}SMTP_SENDER",
}
_PROMPT_FIELDS = (
    _PATH_CUMT_USERNAME,
    _PATH_CUMT_PASSWORD,
    _PATH_QUERY_YEAR,
    _PATH_QUERY_SEMESTER,
    _PATH_CAPTCHA_OPENAI_BASE_URL,
    _PATH_CAPTCHA_OPENAI_API_KEY,
    _PATH_CAPTCHA_OPENAI_MODEL,
)


def load_app_config(args: Namespace) -> AppConfig:
    """Load app configuration from file, environment, and CLI overrides."""

    config_path = resolve_config_path(args.config)
    raw_config = _read_config_file(
        config_path,
        allow_interactive=not bool(getattr(args, "no_interactive", False)),
    )

    return AppConfig(
        config_path=config_path,
        cumt=_build_cumt_config(raw_config),
        query=_build_query_config(raw_config, args),
        http=_build_http_config(raw_config),
        grades=_build_grades_config(raw_config),
        captcha=_build_captcha_config(raw_config),
        notify=_build_notify_config(raw_config),
        logging=_build_logging_config(raw_config),
        output=_build_output_config(raw_config, args),
    )


def resolve_config_path(config_arg: str | None) -> Path:
    """Resolve the configuration path according to project conventions."""

    if config_arg:
        return Path(config_arg).expanduser().resolve()

    search_dirs = (Path.cwd(), Path(__file__).resolve().parents[3])
    for directory in search_dirs:
        for filename in _DEFAULT_CONFIG_NAMES:
            candidate = directory / filename
            if candidate.is_file():
                return candidate.resolve()

    return (Path.cwd() / _DEFAULT_CONFIG_NAMES[0]).resolve()


def _read_config_file(
    config_path: Path,
    *,
    allow_interactive: bool,
) -> dict[str, Any]:
    if not config_path.is_file():
        if allow_interactive and sys.stdin.isatty():
            return _create_interactive_config(config_path)
        raise ConfigError(
            f"Configuration file not found: {config_path}. "
            "Create config.local.json from config.example.json or pass --config."
        )

    try:
        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Configuration file is not valid JSON: {config_path}"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Unable to read configuration file: {config_path}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a JSON object.")
    if allow_interactive and sys.stdin.isatty():
        data = _complete_interactive_config(config_path, data)
    return data


def _create_interactive_config(config_path: Path) -> dict[str, Any]:
    template = _read_config_template()
    completed = _complete_interactive_config(config_path, template)
    _write_config_file(config_path, completed)
    return completed


def _complete_interactive_config(
    config_path: Path,
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    completed = json.loads(json.dumps(raw_config))
    changed = False
    for path in _PROMPT_FIELDS:
        if _get_nested(completed, path):
            continue
        env_name = _env_name_for_path(path)
        if env_name is not None and os.getenv(env_name):
            continue
        value = input(f"{'.'.join(path)}: ").strip()
        if value:
            _set_nested(completed, path, value)
            changed = True
    if changed:
        _write_config_file(config_path, completed)
    return completed


def _read_config_template() -> dict[str, Any]:
    template_path = Path(__file__).resolve().parents[3] / "config.example.json"
    if not template_path.is_file():
        return {}
    try:
        with template_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_config_file(config_path: Path, data: dict[str, Any]) -> None:
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ConfigError(f"Unable to write configuration file: {config_path}") from exc


def _set_nested(raw_config: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    current: dict[str, Any] = raw_config
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _env_name_for_path(path: tuple[str, ...]) -> str | None:
    return _ENV_NAME_BY_PATH.get(path)


def _build_cumt_config(raw_config: dict[str, Any]) -> CUMTConfig:
    return CUMTConfig(
        username=_get_string(
            raw_config,
            _PATH_CUMT_USERNAME,
            env_name=_env_name_for_path(_PATH_CUMT_USERNAME),
            required=True,
        ),
        password=_get_string(
            raw_config,
            _PATH_CUMT_PASSWORD,
            env_name=_env_name_for_path(_PATH_CUMT_PASSWORD),
            required=True,
        ),
    )


def _build_query_config(raw_config: dict[str, Any], args: Namespace) -> QueryConfig:
    return QueryConfig(
        year=(
            str(args.year)
            if args.year is not None
            else _get_string(raw_config, _PATH_QUERY_YEAR, required=True)
        ),
        semester=(
            str(args.semester)
            if args.semester is not None
            else _get_string(raw_config, _PATH_QUERY_SEMESTER, required=True)
        ),
    )


def _build_http_config(raw_config: dict[str, Any]) -> HTTPConfig:
    return HTTPConfig(
        timeout_seconds=_get_float(
            raw_config,
            _PATH_HTTP_TIMEOUT_SECONDS,
            default=30.0,
        ),
        retry_attempts=_get_int(raw_config, _PATH_HTTP_RETRY_ATTEMPTS, default=2),
        retry_backoff_seconds=_get_float(
            raw_config,
            _PATH_HTTP_RETRY_BACKOFF_SECONDS,
            default=1.5,
        ),
    )


def _build_grades_config(raw_config: dict[str, Any]) -> GradesConfig:
    return GradesConfig(
        include_details_on_change=_get_bool(
            raw_config,
            _PATH_GRADES_INCLUDE_DETAILS,
            default=True,
        ),
        detail_concurrency=_get_int(
            raw_config,
            _PATH_GRADES_DETAIL_CONCURRENCY,
            default=3,
        ),
    )


def _build_captcha_config(raw_config: dict[str, Any]) -> CaptchaConfig:
    return CaptchaConfig(
        provider=_get_string(
            raw_config,
            _PATH_CAPTCHA_PROVIDER,
            default="openai_compatible",
        ),
        manual_timeout_seconds=_get_int(
            raw_config,
            _PATH_CAPTCHA_MANUAL_TIMEOUT,
            default=60,
        ),
        openai_compatible=OpenAICompatibleConfig(
            base_url=_get_string(
                raw_config,
                _PATH_CAPTCHA_OPENAI_BASE_URL,
                env_name=_env_name_for_path(_PATH_CAPTCHA_OPENAI_BASE_URL),
                default="",
            ),
            api_key=_get_string(
                raw_config,
                _PATH_CAPTCHA_OPENAI_API_KEY,
                env_name=_env_name_for_path(_PATH_CAPTCHA_OPENAI_API_KEY),
                default="",
            ),
            model=_get_string(
                raw_config,
                _PATH_CAPTCHA_OPENAI_MODEL,
                env_name=_env_name_for_path(_PATH_CAPTCHA_OPENAI_MODEL),
                default="",
            ),
        ),
    )


def _build_notify_config(raw_config: dict[str, Any]) -> NotifyConfig:
    return NotifyConfig(
        enabled=_get_bool(raw_config, _PATH_NOTIFY_ENABLED, default=False),
        smtp_host=_get_string(
            raw_config,
            _PATH_NOTIFY_SMTP_HOST,
            env_name=_env_name_for_path(_PATH_NOTIFY_SMTP_HOST),
            default="",
        ),
        smtp_port=_get_int(raw_config, _PATH_NOTIFY_SMTP_PORT, default=465),
        username=_get_string(
            raw_config,
            _PATH_NOTIFY_USERNAME,
            env_name=_env_name_for_path(_PATH_NOTIFY_USERNAME),
            default="",
        ),
        password=_get_string(
            raw_config,
            _PATH_NOTIFY_PASSWORD,
            env_name=_env_name_for_path(_PATH_NOTIFY_PASSWORD),
            default="",
        ),
        sender=_get_string(
            raw_config,
            _PATH_NOTIFY_SENDER,
            env_name=_env_name_for_path(_PATH_NOTIFY_SENDER),
            default="",
        ),
        sender_name=_get_string(
            raw_config,
            _PATH_NOTIFY_SENDER_NAME,
            default="",
        ),
        recipients=tuple(_get_string_list(raw_config, _PATH_NOTIFY_RECIPIENTS)),
    )


def _build_logging_config(raw_config: dict[str, Any]) -> LoggingConfig:
    return LoggingConfig(
        retention_days=_get_int(raw_config, _PATH_LOGGING_RETENTION_DAYS, default=14)
    )


def _build_output_config(raw_config: dict[str, Any], args: Namespace) -> OutputConfig:
    return OutputConfig(
        save_json=bool(getattr(args, "save_json", False))
        or _get_bool(raw_config, _PATH_OUTPUT_SAVE_JSON, default=False),
        save_report=bool(getattr(args, "save_report", False))
        or _get_bool(raw_config, _PATH_OUTPUT_SAVE_REPORT, default=False),
        save_ics=bool(getattr(args, "save_ics", False))
        or _get_bool(raw_config, _PATH_OUTPUT_SAVE_ICS, default=False),
        output_dir=(
            getattr(args, "output_dir", None)
            if getattr(args, "output_dir", None) is not None
            else _get_string(raw_config, _PATH_OUTPUT_DIR, default="")
        ),
    )


def _get_nested(raw_config: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = raw_config
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _get_string(
    raw_config: dict[str, Any],
    path: tuple[str, ...],
    *,
    env_name: str | None = None,
    required: bool = False,
    default: str | None = None,
) -> str:
    env_value = os.getenv(env_name) if env_name else None
    if env_value not in (None, ""):
        return env_value

    value = _get_nested(raw_config, path)
    if value is None or value == "":
        if required:
            dotted_path = ".".join(path)
            raise ConfigError(f"Missing required configuration: {dotted_path}")
        return default or ""
    if not isinstance(value, str):
        dotted_path = ".".join(path)
        raise ConfigError(f"Configuration {dotted_path} must be a string.")
    return value


def _get_int(
    raw_config: dict[str, Any],
    path: tuple[str, ...],
    *,
    default: int,
) -> int:
    value = _get_nested(raw_config, path)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        dotted_path = ".".join(path)
        raise ConfigError(f"Configuration {dotted_path} must be an integer.")
    return value


def _get_float(
    raw_config: dict[str, Any],
    path: tuple[str, ...],
    *,
    default: float,
) -> float:
    value = _get_nested(raw_config, path)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        dotted_path = ".".join(path)
        raise ConfigError(f"Configuration {dotted_path} must be a number.")
    return float(value)


def _get_bool(
    raw_config: dict[str, Any],
    path: tuple[str, ...],
    *,
    default: bool,
) -> bool:
    value = _get_nested(raw_config, path)
    if value is None:
        return default
    if not isinstance(value, bool):
        dotted_path = ".".join(path)
        raise ConfigError(f"Configuration {dotted_path} must be a boolean.")
    return value


def _get_string_list(raw_config: dict[str, Any], path: tuple[str, ...]) -> list[str]:
    value = _get_nested(raw_config, path)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        dotted_path = ".".join(path)
        raise ConfigError(f"Configuration {dotted_path} must be a list of strings.")
    return list(value)
