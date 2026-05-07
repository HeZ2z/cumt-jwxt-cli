"""Logging setup and sensitive data redaction."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

_SECRET_PATTERNS = (
    re.compile(r"(?i)(password\s*=\s*)[^&\s,;]+"),
    re.compile(r"(?i)(api[_-]?key\s*=\s*)[^&\s,;]+"),
    re.compile(r"(?i)(JSESSIONID\s*=\s*)[^&\s,;]+"),
    re.compile(r"(?i)(route\s*=\s*)[^&\s,;]+"),
    re.compile(r"(?i)(cookie\s*=\s*)[^&\s,;]+"),
)


class SensitiveDataFilter(logging.Filter):
    """Redact known sensitive values before records reach handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub(r"\1***", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(
    *,
    config_path: Path,
    retention_days: int,
    verbose: bool,
) -> None:
    """Configure console and config-adjacent file logging."""

    logs_dir = config_path.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs(logs_dir, retention_days)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    log_filter = SensitiveDataFilter()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.addFilter(log_filter)
    console.setFormatter(logging.Formatter("%(message)s"))

    log_file = logs_dir / f"cumt-jwxt-{date.today().isoformat()}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.addFilter(log_filter)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console)
    root_logger.addHandler(file_handler)


def _cleanup_old_logs(logs_dir: Path, retention_days: int) -> None:
    if retention_days < 1:
        retention_days = 1
    cutoff = datetime.now() - timedelta(days=retention_days)
    for log_path in logs_dir.glob("cumt-jwxt-*.log"):
        try:
            if datetime.fromtimestamp(log_path.stat().st_mtime) < cutoff:
                log_path.unlink()
        except OSError:
            continue
