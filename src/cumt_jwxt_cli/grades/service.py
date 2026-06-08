"""Grade query business orchestration."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from cumt_jwxt_cli.errors import QueryError
from cumt_jwxt_cli.grades.publication import (
    build_publication_artifacts,
    maybe_notify,
    save_optional_outputs,
)
from cumt_jwxt_cli.grades.query_fetch import (
    is_session_query_failure as _is_session_query_failure,
)
from cumt_jwxt_cli.grades.query_fetch import (
    query_grade_details_if_needed,
    query_grade_list,
)
from cumt_jwxt_cli.grades.query_state import (
    build_grade_query_result,
    grade_query_scope_from_config,
    now_iso,
    result_with_details,
    state_with_session,
)
from cumt_jwxt_cli.models import AppConfig, GradeQueryResult, RuntimeState
from cumt_jwxt_cli.notify.email import send_grade_email
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state


def is_session_query_failure(exc: QueryError) -> bool:
    return _is_session_query_failure(exc)


def run_grade_query(
    config: AppConfig,
    client: object,
    *,
    previous_state: RuntimeState | None = None,
    session_cookies: dict[str, str] | None = None,
    session_updated_at: str | None = None,
    force_email: bool,
    now_factory: Callable[[], datetime] | None = None,
    send_email: Callable[..., None] = send_grade_email,
) -> GradeQueryResult:
    """Run the minimal grade-list query workflow and persist safe state."""

    if previous_state is None:
        previous_state = load_runtime_state(config)
    queried_at = now_iso(now_factory)
    scope = grade_query_scope_from_config(config.query.year, config.query.semester)
    grades = query_grade_list(config, client)
    result = build_grade_query_result(
        grades,
        state_with_session(
            previous_state,
            session_cookies=session_cookies,
            session_updated_at=session_updated_at,
        ),
        scope,
        queried_at,
    )
    details = query_grade_details_if_needed(
        config,
        client,
        result,
        force=force_email or config.output.save_report,
        executor_factory=ThreadPoolExecutor,
    )
    result = result_with_details(result, details)

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
        result = build_grade_query_result(
            result.grades,
            state_with_session(
                previous_state,
                session_cookies=session_cookies,
                session_updated_at=session_updated_at,
            ),
            scope,
            queried_at,
            notified_at=notified_at,
        )
        result = result_with_details(result, details)
        state_to_save = result.state

    save_runtime_state(config, state_to_save)
    save_optional_outputs(config, result, artifacts)
    return result
