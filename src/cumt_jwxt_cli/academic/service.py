"""Academic status query business orchestration."""

from __future__ import annotations

from cumt_jwxt_cli.academic.query_fetch import query_academic_summary
from cumt_jwxt_cli.models import AcademicSummaryResult, AppConfig


def run_academic_query(config: AppConfig, client: object) -> AcademicSummaryResult:
    """Fetch cumulative academic status without touching state or notifications."""

    return query_academic_summary(config, client)
