"""Configuration loading for cumt-jwxt-cli."""

from __future__ import annotations

import json
import os
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


def load_app_config(args: Namespace) -> AppConfig:
    """Load app configuration from file, environment, and CLI overrides."""

    config_path = resolve_config_path(args.config)
    raw_config = _read_config_file(config_path)

    cumt_config = CUMTConfig(
        username=_get_string(
            raw_config,
            ("cumt", "username"),
            env_name=f"{_ENV_PREFIX}USERNAME",
            required=True,
        ),
        password=_get_string(
            raw_config,
            ("cumt", "password"),
            env_name=f"{_ENV_PREFIX}PASSWORD",
            required=True,
        ),
    )
    query_config = QueryConfig(
        year=(
            str(args.year)
            if args.year is not None
            else _get_string(raw_config, ("query", "year"), required=True)
        ),
        semester=(
            str(args.semester)
            if args.semester is not None
            else _get_string(raw_config, ("query", "semester"), required=True)
        ),
    )
    http_config = HTTPConfig(
        timeout_seconds=_get_float(
            raw_config, ("http", "timeout_seconds"), default=30.0
        ),
        retry_attempts=_get_int(raw_config, ("http", "retry_attempts"), default=2),
        retry_backoff_seconds=_get_float(
            raw_config,
            ("http", "retry_backoff_seconds"),
            default=1.5,
        ),
    )
    grades_config = GradesConfig(
        include_details_on_change=_get_bool(
            raw_config,
            ("grades", "include_details_on_change"),
            default=True,
        ),
        detail_concurrency=_get_int(
            raw_config,
            ("grades", "detail_concurrency"),
            default=3,
        ),
    )
    captcha_config = CaptchaConfig(
        provider=_get_string(
            raw_config, ("captcha", "provider"), default="openai_compatible"
        ),
        manual_timeout_seconds=_get_int(
            raw_config,
            ("captcha", "manual_timeout_seconds"),
            default=60,
        ),
        openai_compatible=OpenAICompatibleConfig(
            base_url=_get_string(
                raw_config,
                ("captcha", "openai_compatible", "base_url"),
                env_name=f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_BASE_URL",
                default="",
            ),
            api_key=_get_string(
                raw_config,
                ("captcha", "openai_compatible", "api_key"),
                env_name=f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_API_KEY",
                default="",
            ),
            model=_get_string(
                raw_config,
                ("captcha", "openai_compatible", "model"),
                env_name=f"{_ENV_PREFIX}CAPTCHA_OPENAI_COMPATIBLE_MODEL",
                default="",
            ),
        ),
    )
    notify_config = NotifyConfig(
        enabled=_get_bool(raw_config, ("notify", "enabled"), default=False),
        smtp_host=_get_string(
            raw_config,
            ("notify", "smtp_host"),
            env_name=f"{_ENV_PREFIX}SMTP_HOST",
            default="",
        ),
        smtp_port=_get_int(raw_config, ("notify", "smtp_port"), default=465),
        username=_get_string(
            raw_config,
            ("notify", "username"),
            env_name=f"{_ENV_PREFIX}SMTP_USERNAME",
            default="",
        ),
        password=_get_string(
            raw_config,
            ("notify", "password"),
            env_name=f"{_ENV_PREFIX}SMTP_PASSWORD",
            default="",
        ),
        sender=_get_string(
            raw_config,
            ("notify", "sender"),
            env_name=f"{_ENV_PREFIX}SMTP_SENDER",
            default="",
        ),
        recipients=tuple(_get_string_list(raw_config, ("notify", "recipients"))),
    )
    logging_config = LoggingConfig(
        retention_days=_get_int(raw_config, ("logging", "retention_days"), default=14)
    )
    output_config = OutputConfig(
        save_json=bool(args.save_json)
        or _get_bool(raw_config, ("output", "save_json"), default=False),
        save_report=bool(args.save_report)
        or _get_bool(raw_config, ("output", "save_report"), default=False),
        output_dir=(
            args.output_dir
            if args.output_dir is not None
            else _get_string(raw_config, ("output", "output_dir"), default="")
        ),
    )

    return AppConfig(
        config_path=config_path,
        cumt=cumt_config,
        query=query_config,
        http=http_config,
        grades=grades_config,
        captcha=captcha_config,
        notify=notify_config,
        logging=logging_config,
        output=output_config,
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


def _read_config_file(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
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
    return data


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
