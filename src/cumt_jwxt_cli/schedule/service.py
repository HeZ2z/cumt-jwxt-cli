"""Personal schedule query business orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime

from cumt_jwxt_cli.errors import ParseError, QueryError
from cumt_jwxt_cli.models import (
    AppConfig,
    PeriodTime,
    RuntimeState,
    ScheduleQueryResult,
)
from cumt_jwxt_cli.notify.email import send_email
from cumt_jwxt_cli.schedule.publication import (
    build_publication_artifacts,
    maybe_notify,
    save_optional_outputs,
)
from cumt_jwxt_cli.schedule.query_fetch import (
    is_schedule_session_query_failure as _is_schedule_session_query_failure,
)
from cumt_jwxt_cli.schedule.query_fetch import (
    query_period_times,
    query_schedule_list,
    query_week_dates,
)
from cumt_jwxt_cli.schedule.query_state import (
    build_schedule_query_result,
    now_iso,
    schedule_query_scope_from_config,
    state_with_session,
)
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state

logger = logging.getLogger(__name__)


def is_session_query_failure(exc: Exception) -> bool:
    return _is_schedule_session_query_failure(exc)


def run_schedule_query(
    config: AppConfig,
    client: object,
    *,
    previous_state: RuntimeState | None = None,
    session_cookies: dict[str, str] | None = None,
    session_updated_at: str | None = None,
    force_email: bool,
    now_factory: Callable[[], datetime] | None = None,
    send_email_fn: Callable[..., None] = send_email,
) -> ScheduleQueryResult:
    """Run the personal schedule query workflow and persist safe state."""

    if previous_state is None:
        previous_state = load_runtime_state(config)
    queried_at = now_iso(now_factory)
    scope = schedule_query_scope_from_config(config.query.year, config.query.semester)
    list_data = query_schedule_list(config, client)
    period_times = _fetch_period_times(config, client)
    week_dates = _fetch_week_dates(config, client)
    result = build_schedule_query_result(
        list_data.lessons,
        list_data.unscheduled,
        state_with_session(
            previous_state,
            session_cookies=session_cookies,
            session_updated_at=session_updated_at,
        ),
        scope,
        queried_at,
        period_times=period_times,
    )

    artifacts = build_publication_artifacts(
        config,
        result,
        queried_at=queried_at,
        period_times=period_times,
        week_dates=week_dates,
    )
    notified_at = maybe_notify(
        config,
        result,
        artifacts,
        force_email=force_email,
        now_factory=now_factory,
        send_email_fn=send_email_fn,
    )

    state_to_save = result.state
    if notified_at is not None:
        result = build_schedule_query_result(
            list_data.lessons,
            list_data.unscheduled,
            state_with_session(
                previous_state,
                session_cookies=session_cookies,
                session_updated_at=session_updated_at,
            ),
            scope,
            queried_at,
            notified_at=notified_at,
            period_times=period_times,
        )
        state_to_save = result.state

    save_runtime_state(config, state_to_save)
    save_optional_outputs(config, result, artifacts)
    return result


def _fetch_period_times(config: AppConfig, client: object) -> tuple[PeriodTime, ...]:
    # Period times only affect ICS generation; a failure must not lose the
    # schedule snapshot or change detection.
    try:
        return query_period_times(config, client)
    except (QueryError, ParseError) as exc:
        logger.warning("Could not fetch schedule period times: %s", exc)
        return ()


def _fetch_week_dates(config: AppConfig, client: object) -> dict[int, date]:
    try:
        return query_week_dates(config, client)
    except (QueryError, ParseError) as exc:
        logger.warning("Could not fetch schedule week dates: %s", exc)
        return {}
