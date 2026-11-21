"""Course teaching-session query business orchestration."""

from __future__ import annotations

import re

from cumt_jwxt_cli.courses.query_fetch import (
    CourseQueryOptions,
    CourseQueryResult,
    query_course_sessions,
)
from cumt_jwxt_cli.models import AppConfig, CourseSession


def run_course_query(
    config: AppConfig,
    client: object,
    options: CourseQueryOptions,
) -> CourseQueryResult:
    """Fetch, sort, and display-limit course teaching sessions."""

    fetched = query_course_sessions(config, client, options)
    ordered = sorted(fetched.sessions, key=_sort_key)
    if options.limit > 0:
        ordered = ordered[: options.limit]
    return CourseQueryResult(
        sessions=tuple(ordered),
        total=fetched.total,
        year=fetched.year,
        semester=fetched.semester,
    )


def _sort_key(session: CourseSession) -> tuple[int, int, str, str]:
    return (
        _numeric_key(session.weekday, upper=7),
        _period_key(session.periods),
        session.course_code or "",
        session.teacher_name or "",
    )


def _numeric_key(value: str | None, *, upper: int) -> int:
    if value and value.strip().isdigit():
        number = int(value.strip())
        if 1 <= number <= upper:
            return number
    return upper + 1


def _period_key(value: str | None) -> int:
    if not value:
        return 10**6
    match = re.match(r"\s*(\d+)", value)
    if match is None:
        return 10**6
    return int(match.group(1))
