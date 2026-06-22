"""Publication helpers for exam reports, notifications, and optional outputs."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from cumt_jwxt_cli.errors import StateError
from cumt_jwxt_cli.exams.ics import build_ics_content, build_ics_filename
from cumt_jwxt_cli.exams.query_state import now_iso
from cumt_jwxt_cli.exams.report import (
    build_exam_text_summary,
    build_html_report,
    format_term_label,
)
from cumt_jwxt_cli.models import (
    AppConfig,
    ExamChange,
    ExamInfo,
    ExamQueryResult,
    ExamSnapshotEntry,
)
from cumt_jwxt_cli.notify.email import send_email
from cumt_jwxt_cli.output_naming import short_year_semester


@dataclass(frozen=True)
class PublicationArtifacts:
    text_summary: str
    html_report: str
    ics_content: str


def build_publication_artifacts(
    config: AppConfig,
    result: ExamQueryResult,
    *,
    queried_at: str,
) -> PublicationArtifacts:
    return PublicationArtifacts(
        text_summary=build_exam_text_summary(
            exams=result.exams,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
        ),
        html_report=build_html_report(
            exams=result.exams,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
        ),
        ics_content=build_ics_content(
            exams=result.exams,
            year=config.query.year,
            semester=config.query.semester,
        ),
    )


def maybe_notify(
    config: AppConfig,
    result: ExamQueryResult,
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
            f"CUMT 考试报告 "
            f"{format_term_label(config.query.year, config.query.semester)}"
        ),
        text_body=artifacts.text_summary,
        html_body=artifacts.html_report,
        attachments=attachments,
    )
    return notified_at


def save_optional_outputs(
    config: AppConfig,
    result: ExamQueryResult,
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
            (output_dir / f"exams_{suffix}.json").write_text(
                json.dumps(
                    build_exams_json_payload(result, artifacts.text_summary),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        if config.output.save_report:
            (output_dir / f"exam_report_{suffix}.html").write_text(
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
            )
    except OSError as exc:
        raise StateError(f"Could not save optional outputs: {exc}") from exc


def build_exams_json_payload(
    result: ExamQueryResult,
    text_summary: str,
) -> dict[str, object]:
    return {
        "exams": [serialize_exam_info(exam) for exam in result.exams],
        "changes": [serialize_exam_change(change) for change in result.changes],
        "summary": text_summary,
    }


def serialize_exam_info(exam: ExamInfo) -> dict[str, str | None]:
    return {
        "course_code": exam.course_code,
        "course_name": exam.course_name,
        "exam_time": exam.exam_time,
        "location": exam.location,
        "campus": exam.campus,
        "exam_name": exam.exam_name,
        "exam_method": exam.exam_method,
        "class_schedule": exam.class_schedule,
        "teacher_info": exam.teacher_info,
        "credit": exam.credit,
    }


def serialize_exam_change(change: ExamChange) -> dict[str, object]:
    return {
        "change_type": change.change_type,
        "before": (
            None
            if change.before is None
            else serialize_exam_snapshot_entry(change.before)
        ),
        "after": (
            None
            if change.after is None
            else serialize_exam_snapshot_entry(change.after)
        ),
    }


def serialize_exam_snapshot_entry(
    entry: ExamSnapshotEntry,
) -> dict[str, str | None]:
    return {
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "exam_time": entry.exam_time,
        "location": entry.location,
        "campus": entry.campus,
        "exam_name": entry.exam_name,
        "exam_method": entry.exam_method,
    }
