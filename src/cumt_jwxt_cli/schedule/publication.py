"""Publication helpers for schedule reports, notifications, and optional outputs."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.models import (
    AppConfig,
    PeriodTime,
    ScheduleChange,
    ScheduleLesson,
    ScheduleQueryResult,
    ScheduleSlot,
    ScheduleSnapshotEntry,
    ScheduleUnscheduledCourse,
)
from cumt_jwxt_cli.notify.email import send_email
from cumt_jwxt_cli.output_naming import short_year_semester
from cumt_jwxt_cli.schedule.ics import build_ics_content, build_ics_filename
from cumt_jwxt_cli.schedule.query_state import now_iso
from cumt_jwxt_cli.schedule.report import (
    build_html_report,
    build_schedule_text_summary,
    format_term_label,
)


@dataclass(frozen=True)
class PublicationArtifacts:
    text_summary: str
    html_report: str
    ics_content: str


def build_publication_artifacts(
    config: AppConfig,
    result: ScheduleQueryResult,
    *,
    queried_at: str,
    period_times: Sequence[PeriodTime] = (),
    week_dates: Mapping[int, date] | None = None,
) -> PublicationArtifacts:
    return PublicationArtifacts(
        text_summary=build_schedule_text_summary(
            lessons=result.lessons,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
            period_times=period_times,
        ),
        html_report=build_html_report(
            lessons=result.lessons,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
            period_times=period_times,
        ),
        ics_content=build_ics_content(
            result.lessons,
            period_times,
            {} if week_dates is None else week_dates,
            config.query.year,
            config.query.semester,
        ),
    )


def maybe_notify(
    config: AppConfig,
    result: ScheduleQueryResult,
    artifacts: PublicationArtifacts,
    *,
    force_email: bool,
    now_factory: Callable[[], datetime] | None = None,
    send_email_fn: Callable[..., None] = send_email,
) -> str | None:
    should_notify = bool(result.changes) or force_email
    if not config.notify.enabled or not should_notify:
        return None

    notified_at = now_iso(now_factory)
    attachments: list[tuple[str, bytes, str]] = [
        (
            build_ics_filename(config.query.year, config.query.semester),
            artifacts.ics_content.encode("utf-8"),
            "text/calendar",
        ),
    ]
    send_email_fn(
        config.notify,
        subject=(
            f"CUMT 课表报告 "
            f"{format_term_label(config.query.year, config.query.semester)}"
        ),
        text_body=artifacts.text_summary,
        html_body=artifacts.html_report,
        attachments=attachments,
    )
    return notified_at


def save_optional_outputs(
    config: AppConfig,
    result: ScheduleQueryResult,
    artifacts: PublicationArtifacts,
) -> None:
    if (
        not config.output.save_json
        and not config.output.save_report
        and not config.output.save_ics
    ):
        return

    try:
        output_dir = config.output.resolve_dir(config.config_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        suffix = short_year_semester(config.query.year, config.query.semester)

        if config.output.save_json:
            (output_dir / f"schedules_{suffix}.json").write_text(
                json.dumps(
                    build_schedules_json_payload(result, artifacts.text_summary),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        if config.output.save_report:
            (output_dir / f"schedule_report_{suffix}.html").write_text(
                artifacts.html_report,
                encoding="utf-8",
            )
        if config.output.save_ics:
            (
                output_dir
                / build_ics_filename(config.query.year, config.query.semester)
            ).write_text(
                artifacts.ics_content,
                encoding="utf-8",
                # icalendar uses CRLF; disable newline translation so the file
                # keeps its exact line endings instead of becoming \r\r\n.
                newline="\n",
            )
    except OSError as exc:
        raise StateError(f"Could not save optional outputs: {exc}") from exc


def build_schedules_json_payload(
    result: ScheduleQueryResult,
    text_summary: str,
) -> dict[str, object]:
    return {
        "lessons": [serialize_schedule_lesson(lesson) for lesson in result.lessons],
        "unscheduled": [
            serialize_schedule_unscheduled_course(course)
            for course in result.unscheduled
        ],
        "changes": [serialize_schedule_change(change) for change in result.changes],
        "summary": text_summary,
    }


def serialize_schedule_lesson(lesson: ScheduleLesson) -> dict[str, object]:
    return {
        "course_code": lesson.course_code,
        "course_name": lesson.course_name,
        "teaching_class": lesson.teaching_class,
        "teacher": lesson.teacher,
        "credits": lesson.credits,
        "course_type": lesson.course_type,
        "slots": [serialize_schedule_slot(slot) for slot in lesson.slots],
    }


def serialize_schedule_unscheduled_course(
    course: ScheduleUnscheduledCourse,
) -> dict[str, str | None]:
    return {
        "course_name": course.course_name,
        "teacher": course.teacher,
        "week_range": course.week_range,
        "credits": course.credits,
    }


def serialize_schedule_change(change: ScheduleChange) -> dict[str, object]:
    return {
        "change_type": change.change_type,
        "before": (
            None
            if change.before is None
            else serialize_schedule_snapshot_entry(change.before)
        ),
        "after": (
            None
            if change.after is None
            else serialize_schedule_snapshot_entry(change.after)
        ),
    }


def serialize_schedule_snapshot_entry(
    entry: ScheduleSnapshotEntry,
) -> dict[str, object]:
    return {
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "teaching_class": entry.teaching_class,
        "teacher": entry.teacher,
        "slots": [serialize_schedule_slot(slot) for slot in entry.slots],
    }


def serialize_schedule_slot(slot: ScheduleSlot) -> dict[str, object]:
    return {
        "weekday": slot.weekday,
        "periods": slot.periods,
        "weeks": list(slot.weeks),
        "location": slot.location,
    }
