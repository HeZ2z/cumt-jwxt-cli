"""Session-oriented query use cases."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from cumt_jwxt_cli.captcha.ddddocr_ocr import recognize_captcha
from cumt_jwxt_cli.client.auth import login
from cumt_jwxt_cli.client.http import JWXTClient
from cumt_jwxt_cli.errors import QueryError
from cumt_jwxt_cli.exams.query_fetch import is_exam_session_query_failure
from cumt_jwxt_cli.exams.service import run_exam_query
from cumt_jwxt_cli.grades.service import is_session_query_failure, run_grade_query
from cumt_jwxt_cli.models import (
    AppConfig,
    ExamQueryResult,
    GradeQueryResult,
    ScheduleQueryResult,
)
from cumt_jwxt_cli.schedule.query_fetch import is_schedule_session_query_failure
from cumt_jwxt_cli.schedule.service import run_schedule_query
from cumt_jwxt_cli.state import load_runtime_state
from cumt_jwxt_cli.time_utils import utc_now_iso

_ResultT = TypeVar("_ResultT")


def query_grades_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> GradeQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    return _query_with_session_reuse(
        config,
        run_query=run_grade_query,
        is_session_failure=is_session_query_failure,
        force_email=force_email,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
    )


def query_exams_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> ExamQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    return _query_with_session_reuse(
        config,
        run_query=run_exam_query,
        is_session_failure=is_exam_session_query_failure,
        force_email=force_email,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
    )


def query_schedule_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool = True,
) -> ScheduleQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

    return _query_with_session_reuse(
        config,
        run_query=run_schedule_query,
        is_session_failure=is_schedule_session_query_failure,
        force_email=force_email,
        trust_env=trust_env,
        allow_manual_captcha=allow_manual_captcha,
    )


def _query_with_session_reuse(
    config: AppConfig,
    *,
    run_query: Callable[..., _ResultT],
    is_session_failure: Callable[[QueryError], bool],
    force_email: bool,
    trust_env: bool,
    allow_manual_captcha: bool,
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

        try:
            return run_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=session_updated_at,
                force_email=force_email,
            )
        except QueryError as exc:
            if not previous_state.session_cookies or not is_session_failure(exc):
                raise

            client.reset_session()
            _login(config, client, allow_manual_captcha=allow_manual_captcha)
            return run_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=_now_iso(),
                force_email=force_email,
            )


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
