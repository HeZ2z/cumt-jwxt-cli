"""Session-oriented query use cases."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import TypeVar

from cumt_jwxt_cli.academic.query_fetch import is_academic_session_query_failure
from cumt_jwxt_cli.academic.service import run_academic_query
from cumt_jwxt_cli.captcha.ddddocr_ocr import recognize_captcha
from cumt_jwxt_cli.classrooms.query_fetch import (
    ClassroomQueryOptions,
    ClassroomQueryResult,
    is_classroom_session_query_failure,
)
from cumt_jwxt_cli.classrooms.service import run_classroom_query
from cumt_jwxt_cli.client.auth import login
from cumt_jwxt_cli.client.http import JWXTClient
from cumt_jwxt_cli.client.term import resolve_current_term
from cumt_jwxt_cli.courses.query_fetch import (
    CourseQueryOptions,
    CourseQueryResult,
    is_course_session_query_failure,
)
from cumt_jwxt_cli.courses.service import run_course_query
from cumt_jwxt_cli.errors import QueryError, SessionExpiredError
from cumt_jwxt_cli.exams.query_fetch import is_exam_session_query_failure
from cumt_jwxt_cli.exams.service import run_exam_query
from cumt_jwxt_cli.grades.service import is_session_query_failure, run_grade_query
from cumt_jwxt_cli.models import (
    AcademicSummaryResult,
    AppConfig,
    ExamQueryResult,
    GradeQueryResult,
    QueryConfig,
    RuntimeState,
    ScheduleQueryResult,
)
from cumt_jwxt_cli.schedule.query_fetch import is_schedule_session_query_failure
from cumt_jwxt_cli.schedule.service import run_schedule_query
from cumt_jwxt_cli.state import load_runtime_state
from cumt_jwxt_cli.time_utils import resolve_query_scope, utc_now_iso

_ResultT = TypeVar("_ResultT")
logger = logging.getLogger(__name__)


def query_grades_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> GradeQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    def action(
        config: AppConfig,
        client: object,
        previous_state: RuntimeState,
        session_updated_at: str | None,
    ) -> GradeQueryResult:
        return run_grade_query(
            config,
            client,
            previous_state=previous_state,
            session_cookies=client.export_cookies(),
            session_updated_at=session_updated_at,
            force_email=force_email,
        )

    return _with_session(
        config,
        action=action,
        is_session_failure=is_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=True,
    )


def query_exams_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> ExamQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    def action(
        config: AppConfig,
        client: object,
        previous_state: RuntimeState,
        session_updated_at: str | None,
    ) -> ExamQueryResult:
        return run_exam_query(
            config,
            client,
            previous_state=previous_state,
            session_cookies=client.export_cookies(),
            session_updated_at=session_updated_at,
            force_email=force_email,
        )

    return _with_session(
        config,
        action=action,
        is_session_failure=is_exam_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=True,
    )


def query_schedule_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> ScheduleQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    def action(
        config: AppConfig,
        client: object,
        previous_state: RuntimeState,
        session_updated_at: str | None,
    ) -> ScheduleQueryResult:
        return run_schedule_query(
            config,
            client,
            previous_state=previous_state,
            session_cookies=client.export_cookies(),
            session_updated_at=session_updated_at,
            force_email=force_email,
        )

    return _with_session(
        config,
        action=action,
        is_session_failure=is_schedule_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=True,
    )


def query_classrooms_with_session_reuse(
    config: AppConfig,
    *,
    options: ClassroomQueryOptions,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> ClassroomQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    def action(
        config: AppConfig,
        client: object,
        _previous_state: RuntimeState,
        _session_updated_at: str | None,
    ) -> ClassroomQueryResult:
        return run_classroom_query(config, client, options)

    return _with_session(
        config,
        action=action,
        is_session_failure=is_classroom_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=True,
    )


def query_courses_with_session_reuse(
    config: AppConfig,
    *,
    options: CourseQueryOptions,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> CourseQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry.

    Course queries are read-only and never write state or send notifications.
    """

    def action(
        config: AppConfig,
        client: object,
        _previous_state: RuntimeState,
        _session_updated_at: str | None,
    ) -> CourseQueryResult:
        return run_course_query(config, client, options)

    return _with_session(
        config,
        action=action,
        is_session_failure=is_course_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=True,
    )


def query_academic_with_session_reuse(
    config: AppConfig,
    *,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> AcademicSummaryResult:
    """Reuse saved session cookies and retry once after session expiry.

    Academic status is read-only and cumulative, so this never writes state or
    triggers notifications.
    """

    def action(
        config: AppConfig,
        client: object,
        _previous_state: RuntimeState,
        _session_updated_at: str | None,
    ) -> AcademicSummaryResult:
        return run_academic_query(config, client)

    return _with_session(
        config,
        action=action,
        is_session_failure=is_academic_session_query_failure,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
        resolve_scope=False,
    )


def _with_session(
    config: AppConfig,
    *,
    action: Callable[[AppConfig, object, RuntimeState, str | None], _ResultT],
    is_session_failure: Callable[[QueryError], bool],
    trust_env: bool,
    allow_manual_captcha: bool,
    resolve_scope: bool,
) -> _ResultT:
    previous_state = load_runtime_state(config)
    with JWXTClient(
        timeout_seconds=config.http.timeout_seconds,
        retry_attempts=config.http.retry_attempts,
        retry_backoff_seconds=config.http.retry_backoff_seconds,
        trust_env=trust_env,
    ) as client:
        client.load_cookies(previous_state.session_cookies)
        client.check_reachable()

        session_updated_at = None
        if not previous_state.session_cookies:
            _login(config, client, allow_manual_captcha=allow_manual_captcha)
            session_updated_at = _now_iso()

        resolved_config: AppConfig | None = None
        try:
            resolved_config = _resolve_scope_config(
                config, client, resolve_scope=resolve_scope
            )
            return action(resolved_config, client, previous_state, session_updated_at)
        except QueryError as exc:
            if not is_session_failure(exc):
                raise
            # A failure while resolving the term happens before any action ran,
            # so it is always worth one fresh login. For action failures keep the
            # existing guard: only stale saved cookies are retried.
            scope_failed = resolved_config is None
            if not previous_state.session_cookies and not scope_failed:
                raise

            client.reset_session()
            _login(config, client, allow_manual_captcha=allow_manual_captcha)
            resolved_config = _resolve_scope_config(
                config, client, resolve_scope=resolve_scope
            )
            return action(
                resolved_config,
                client,
                previous_state,
                _now_iso(),
            )


def _resolve_scope_config(
    config: AppConfig,
    client: object,
    *,
    resolve_scope: bool,
) -> AppConfig:
    """Fill an empty auto query scope from JWXT, falling back to the calendar."""

    if not resolve_scope:
        return config
    query = getattr(config, "query", None)
    if query is None or getattr(query, "year", ""):
        return config

    try:
        term = resolve_current_term(client)
    except SessionExpiredError:
        raise
    except QueryError as exc:
        logger.warning(
            "Could not read the current JWXT term (%s); falling back to calendar.",
            exc,
        )
        term = None

    if term is None:
        year, semester = resolve_query_scope()
        logger.warning(
            "JWXT current term unavailable; using calendar scope %s/%s.",
            year,
            semester,
        )
    else:
        year, semester = term
        logger.debug("Resolved current JWXT term: %s/%s.", year, semester)
    return _config_with_scope(config, year, semester)


def _config_with_scope(config: AppConfig, year: str, semester: str) -> AppConfig:
    query = QueryConfig(year=year, semester=semester, auto=True)
    if dataclasses.is_dataclass(config):
        return dataclasses.replace(config, query=query)
    # Lightweight test doubles are mutable namespaces rather than dataclasses.
    config.query = query  # type: ignore[attr-defined]
    return config


def _login(
    config: AppConfig,
    client: JWXTClient,
    *,
    allow_manual_captcha: bool = True,
) -> None:
    # auth.login() calls the callback as (image, config); accepting config here
    # keeps the closure signature in sync with that contract.
    def recognize(image: bytes, _config: AppConfig) -> str:
        return _recognize_captcha_with_config(
            image,
            config,
            allow_manual_captcha=allow_manual_captcha,
        )

    login(config, client, recognize_captcha=recognize)


def _recognize_captcha_with_config(
    image: bytes,
    config: AppConfig,
    *,
    allow_manual_captcha: bool = True,
) -> str:
    return recognize_captcha(
        image,
        manual_timeout_seconds=(
            config.captcha.manual_timeout_seconds if allow_manual_captcha else None
        ),
    )


def _now_iso() -> str:
    return utc_now_iso()
