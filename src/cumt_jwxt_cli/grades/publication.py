"""Publication helpers for reports, notifications, and optional outputs."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from cumt_jwxt_cli.grades.query_state import now_iso
from cumt_jwxt_cli.grades.report import (
    build_html_report,
    build_text_summary,
    format_term_label,
)
from cumt_jwxt_cli.models import (
    AppConfig,
    CourseGrade,
    GradeChange,
    GradeDetail,
    GradeDetailComponent,
    GradeQueryResult,
    GradeSnapshotEntry,
)
from cumt_jwxt_cli.notify.email import send_grade_email


@dataclass(frozen=True)
class PublicationArtifacts:
    text_summary: str
    html_report: str


def build_publication_artifacts(
    config: AppConfig,
    result: GradeQueryResult,
    *,
    queried_at: str,
) -> PublicationArtifacts:
    return PublicationArtifacts(
        text_summary=build_text_summary(
            grades=result.grades,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
        ),
        html_report=build_html_report(
            grades=result.grades,
            changes=result.changes,
            details=result.details,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
        ),
    )


def maybe_notify(
    config: AppConfig,
    result: GradeQueryResult,
    artifacts: PublicationArtifacts,
    *,
    force_email: bool,
    now_factory: Callable[[], datetime] | None = None,
    send_email: Callable[..., None] = send_grade_email,
) -> str | None:
    should_notify = bool(result.changes) or force_email
    if not config.notify.enabled or not should_notify:
        return None

    notified_at = now_iso(now_factory)
    send_email(
        config.notify,
        subject=(
            f"CUMT 成绩报告 "
            f"{format_term_label(config.query.year, config.query.semester)}"
        ),
        text_body=artifacts.text_summary,
        html_body=artifacts.html_report,
    )
    return notified_at


def save_optional_outputs(
    config: AppConfig,
    result: GradeQueryResult,
    artifacts: PublicationArtifacts,
) -> None:
    if not config.output.save_json and not config.output.save_report:
        return

    output_dir = config.output.resolve_dir(config.config_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if config.output.save_json:
        (output_dir / "grades.json").write_text(
            json.dumps(
                build_grades_json_payload(result, artifacts.text_summary),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if config.output.save_report:
        (output_dir / "grade_report.html").write_text(
            artifacts.html_report,
            encoding="utf-8",
        )


def build_grades_json_payload(
    result: GradeQueryResult,
    text_summary: str,
) -> dict[str, object]:
    """Build the stable public JSON artifact without exposing runtime state."""

    return {
        "grades": [serialize_course_grade(grade) for grade in result.grades],
        "changes": [serialize_grade_change(change) for change in result.changes],
        "details": [serialize_grade_detail(detail) for detail in result.details],
        "summary": text_summary,
    }


def serialize_course_grade(grade: CourseGrade) -> dict[str, str | None]:
    return {
        "course_code": grade.course_code,
        "course_name": grade.course_name,
        "score": grade.score,
        "credit": grade.credit,
        "grade_point": grade.grade_point,
        "credit_grade_point": grade.credit_grade_point,
        "course_type": grade.course_type,
        "exam_type": grade.exam_type,
        "teacher_name": grade.teacher_name,
        "teaching_class_id": grade.teaching_class_id,
    }


def serialize_grade_change(change: GradeChange) -> dict[str, object]:
    return {
        "change_type": change.change_type,
        "before": (
            None if change.before is None else serialize_snapshot_entry(change.before)
        ),
        "after": (
            None if change.after is None else serialize_snapshot_entry(change.after)
        ),
    }


def serialize_snapshot_entry(entry: GradeSnapshotEntry) -> dict[str, str]:
    return {
        "course_code": entry.course_code,
        "course_name": entry.course_name,
        "score": entry.score,
    }


def serialize_grade_detail(detail: GradeDetail) -> dict[str, object]:
    return {
        "course_code": detail.course_code,
        "course_name": detail.course_name,
        "components": [
            serialize_grade_detail_component(component)
            for component in detail.components
        ],
    }


def serialize_grade_detail_component(
    component: GradeDetailComponent,
) -> dict[str, str]:
    return {
        "name": component.name,
        "percentage": component.percentage,
        "score": component.score,
    }
