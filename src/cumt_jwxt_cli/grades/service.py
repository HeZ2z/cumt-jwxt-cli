"""Grade query business orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from cumt_jwxt_cli.errors import QueryError, StateError
from cumt_jwxt_cli.grades.parser import parse_grade_list
from cumt_jwxt_cli.grades.report import build_html_report, build_text_summary
from cumt_jwxt_cli.grades.snapshot import compare_snapshots, create_grade_snapshot
from cumt_jwxt_cli.models import AppConfig, CourseGrade, GradeQueryResult, RuntimeState
from cumt_jwxt_cli.notify.email import send_grade_email
from cumt_jwxt_cli.state import load_runtime_state, save_runtime_state

GRADE_LIST_PATH = "/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"


def build_grade_query_result(
    grades: Iterable[CourseGrade],
    previous_state: RuntimeState,
    queried_at: str,
    notified_at: str | None = None,
) -> GradeQueryResult:
    """Build snapshot, changes, and next runtime state from parsed grades."""

    grade_records = tuple(grades)
    current_snapshot = create_grade_snapshot(list(grade_records))
    changes = tuple(
        compare_snapshots(previous_state.last_grade_snapshot, current_snapshot)
    )
    normalized_queried_at = _required_iso_timestamp(
        queried_at, "last_successful_query_at"
    )
    normalized_notified_at = _optional_iso_timestamp(
        notified_at, "last_notified_at"
    )

    next_state = RuntimeState(
        schema_version=previous_state.schema_version,
        session_cookies=dict(previous_state.session_cookies),
        session_updated_at=previous_state.session_updated_at,
        last_grade_snapshot=current_snapshot,
        last_successful_query_at=normalized_queried_at,
        last_notified_at=(
            previous_state.last_notified_at
            if normalized_notified_at is None
            else normalized_notified_at
        ),
    )
    return GradeQueryResult(
        grades=grade_records,
        snapshot=current_snapshot,
        changes=changes,
        state=next_state,
    )


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
    queried_at = _now_iso(now_factory)
    payload = _query_grade_list(config, client)
    grades = parse_grade_list(payload)
    result = build_grade_query_result(
        grades,
        _state_with_session(
            previous_state,
            session_cookies=session_cookies,
            session_updated_at=session_updated_at,
        ),
        queried_at,
    )

    text_summary = build_text_summary(
        grades=result.grades,
        changes=result.changes,
        year=config.query.year,
        semester=config.query.semester,
        queried_at=queried_at,
    )
    html_report = build_html_report(
        grades=result.grades,
        changes=result.changes,
        year=config.query.year,
        semester=config.query.semester,
        queried_at=queried_at,
    )

    should_notify = bool(result.changes) or force_email
    state_to_save = result.state
    if config.notify.enabled and should_notify:
        notified_at = _now_iso(now_factory)
        send_email(
            config.notify,
            subject=f"CUMT grades {config.query.year}-{config.query.semester}",
            text_body=text_summary,
            html_body=html_report,
        )
        result = build_grade_query_result(
            result.grades,
            _state_with_session(
                previous_state,
                session_cookies=session_cookies,
                session_updated_at=session_updated_at,
            ),
            queried_at,
            notified_at=notified_at,
        )
        state_to_save = result.state

    save_runtime_state(config, state_to_save)
    _save_optional_outputs(config, result, text_summary, html_report)
    return result


def is_session_query_failure(exc: QueryError) -> bool:
    """Return whether a query failure likely indicates an expired login session."""

    message = str(exc).lower()
    session_markers = (
        "http 901",
        "not valid json",
        "invalid response object",
    )
    return any(marker in message for marker in session_markers)


def _query_grade_list(config: AppConfig, client: object) -> object:
    try:
        response = client.post(
            GRADE_LIST_PATH,
            data={
                "xnm": config.query.year,
                "xqm": config.query.semester,
                "sfzgcj": "",
                "kcbj": "",
                "_search": "false",
                "queryModel.showCount": "100",
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": "13",
            },
        )
        content_type = ""
        headers = getattr(response, "headers", None)
        if isinstance(headers, dict):
            content_type = str(headers.get("content-type", "")).lower()
        status_code = getattr(response, "status_code", None)
        if status_code == 901:
            raise QueryError("JWXT grade list request failed with HTTP 901.")
        if "text/html" in content_type:
            raise QueryError(
                "JWXT grade list response looks like an HTML login page."
            )
        return response.json()
    except ValueError as exc:
        raise QueryError("JWXT grade list response is not valid JSON.") from exc
    except AttributeError as exc:
        raise QueryError("JWXT client returned an invalid response object.") from exc


def _state_with_session(
    previous_state: RuntimeState,
    *,
    session_cookies: dict[str, str] | None,
    session_updated_at: str | None,
) -> RuntimeState:
    cookies = (
        previous_state.session_cookies if session_cookies is None else session_cookies
    )
    return RuntimeState(
        schema_version=previous_state.schema_version,
        session_cookies=dict(cookies),
        session_updated_at=(
            previous_state.session_updated_at
            if session_updated_at is None
            else session_updated_at
        ),
        last_grade_snapshot=previous_state.last_grade_snapshot,
        last_successful_query_at=previous_state.last_successful_query_at,
        last_notified_at=previous_state.last_notified_at,
    )


def _save_optional_outputs(
    config: AppConfig,
    result: GradeQueryResult,
    text_summary: str,
    html_report: str,
) -> None:
    if not config.output.save_json and not config.output.save_report:
        return

    output_dir = (
        Path(config.output.output_dir).expanduser()
        if config.output.output_dir
        else config.config_path.parent / "output"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    if config.output.save_json:
        payload = {
            "grades": [grade.__dict__ for grade in result.grades],
            "changes": [
                {
                    "change_type": change.change_type,
                    "before": None if change.before is None else change.before.__dict__,
                    "after": None if change.after is None else change.after.__dict__,
                }
                for change in result.changes
            ],
            "summary": text_summary,
        }
        (output_dir / "grades.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if config.output.save_report:
        (output_dir / "grade_report.html").write_text(html_report, encoding="utf-8")


def _now_iso(now_factory: Callable[[], datetime] | None) -> str:
    now = now_factory() if now_factory is not None else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.isoformat()


def _required_iso_timestamp(value: object, field_name: str) -> str:
    if value is None:
        raise StateError(f"State field {field_name} must be a string or null.")
    return _optional_iso_timestamp(value, field_name)  # type: ignore[return-value]


def _optional_iso_timestamp(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateError(f"State field {field_name} must be a string or null.")

    stripped = value.strip()
    if not stripped:
        raise StateError(f"State field {field_name} must not be blank when present.")

    value_to_parse = (
        stripped.removesuffix("Z") + "+00:00" if stripped.endswith("Z") else stripped
    )
    try:
        datetime.fromisoformat(value_to_parse)
    except ValueError as exc:
        raise StateError(
            f"State field {field_name} must be an ISO 8601 timestamp."
        ) from exc
    return stripped
