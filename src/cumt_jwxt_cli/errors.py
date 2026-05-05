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
