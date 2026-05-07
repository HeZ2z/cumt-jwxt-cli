"""Error and exit code definitions."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes used by the CLI."""

    OK = 0
    UNKNOWN = 1
    CONFIG_ERROR = 2
    AUTH_ERROR = 3
    QUERY_ERROR = 4
    PARSE_ERROR = 5
    NOTIFY_ERROR = 6


class CUMTJWXTError(Exception):
    """Base class for project errors safe to show in CLI output."""


class ConfigError(CUMTJWXTError):
    """Raised when configuration is missing or invalid."""


class AuthError(CUMTJWXTError):
    """Raised when JWXT authentication fails."""


class CaptchaError(CUMTJWXTError):
    """Raised when captcha recognition or manual input fails."""


class QueryError(CUMTJWXTError):
    """Raised when JWXT grade queries fail."""


class ParseError(CUMTJWXTError):
    """Raised when external grade data cannot be parsed safely."""


class NotifyError(CUMTJWXTError):
    """Raised when notification delivery fails."""


class SnapshotError(CUMTJWXTError):
    """Raised when grade snapshots are ambiguous or unsupported."""


class StateError(CUMTJWXTError):
    """Raised when runtime state cannot be read or written safely."""
