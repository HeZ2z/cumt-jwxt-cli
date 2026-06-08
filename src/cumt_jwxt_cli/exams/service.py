"""Exam query business orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from cumt_jwxt_cli.exams.publication import (
    build_publication_artifacts,
    maybe_notify,
    save_optional_outputs,
)
from cumt_jwxt_cli.exams.query_fetch import (
    is_exam_session_query_failure as _is_exam_session_query_failure,
)
from cumt_jwxt_cli.exams.query_fetch import query_exam_list
from cumt_jwxt_cli.exams.query_state import (
    build_exam_query_result,
    exam_query_scope_from_config,
    now_iso,
    state_with_session,
)
from cumt_jwxt_cli.models import AppConfig, ExamQueryResult, RuntimeState
from cumt_jwxt_cli.notify.email import send_grade_email
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state


def is_session_query_failure(exc: Exception) -> bool:
    return _is_exam_session_query_failure(exc)


def run_exam_query(
    config: AppConfig,
    client: object,
    *,
    previous_state: RuntimeState | None = None,
    session_cookies: dict[str, str] | None = None,
    session_updated_at: str | None = None,
    force_email: bool,
    now_factory: Callable[[], datetime] | None = None,
    send_email: Callable[..., None] = send_grade_email,
) -> ExamQueryResult:
    """Run the exam query workflow and persist safe state."""

    if previous_state is None:
        previous_state = load_runtime_state(config)
    queried_at = now_iso(now_factory)
    scope = exam_query_scope_from_config(config.query.year, config.query.semester)
    exams = query_exam_list(config, client)
    result = build_exam_query_result(
        exams,
        state_with_session(
            previous_state,
            session_cookies=session_cookies,
            session_updated_at=session_updated_at,
        ),
        scope,
        queried_at,
    )

    artifacts = build_publication_artifacts(config, result, queried_at=queried_at)
    notified_at = maybe_notify(
        config,
        result,
        artifacts,
        force_email=force_email,
        now_factory=now_factory,
        send_email=send_email,
    )

    state_to_save = result.state
    if notified_at is not None:
        result = build_exam_query_result(
            result.exams,
            state_with_session(
                previous_state,
                session_cookies=session_cookies,
                session_updated_at=session_updated_at,
            ),
            scope,
            queried_at,
            notified_at=notified_at,
        )
        state_to_save = result.state

    save_runtime_state(config, state_to_save)
    save_optional_outputs(config, result, artifacts)
    return result
