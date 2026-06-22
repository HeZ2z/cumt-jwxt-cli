"""Session-oriented query use cases."""

from __future__ import annotations

from cumt_jwxt_cli.captcha.openai_compatible import recognize_captcha
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
)
from cumt_jwxt_cli.state import load_runtime_state
from cumt_jwxt_cli.time_utils import utc_now_iso


def query_grades_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
) -> GradeQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

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
            _login(config, client)
            session_updated_at = _now_iso()

        try:
            return run_grade_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=session_updated_at,
                force_email=force_email,
            )
        except QueryError as exc:
            if not previous_state.session_cookies or not is_session_query_failure(exc):
                raise

            client.reset_session()
            _login(config, client)
            return run_grade_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=_now_iso(),
                force_email=force_email,
            )


def _login(config: AppConfig, client: JWXTClient) -> None:
    login(config, client, recognize_captcha=_recognize_captcha_with_config)


def _recognize_captcha_with_config(image: bytes, config: AppConfig) -> str:
    return recognize_captcha(
        image,
        config.captcha.openai_compatible,
        manual_timeout_seconds=config.captcha.manual_timeout_seconds,
    )


def _now_iso() -> str:
    return utc_now_iso()


def query_exams_with_session_reuse(
    config: AppConfig,
    *,
    force_email: bool,
    trust_env: bool,
) -> ExamQueryResult:
    """Load state, reuse session cookies, and retry once after session expiry."""

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
            _login(config, client)
            session_updated_at = _now_iso()

        try:
            return run_exam_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=session_updated_at,
                force_email=force_email,
            )
        except QueryError as exc:
            if not previous_state.session_cookies or not is_exam_session_query_failure(
                exc
            ):
                raise

            client.reset_session()
            _login(config, client)
            return run_exam_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.export_cookies(),
                session_updated_at=_now_iso(),
                force_email=force_email,
            )
