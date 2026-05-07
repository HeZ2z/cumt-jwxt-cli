"""Core data models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class CUMTConfig:
    """CUMT JWXT account configuration."""

    username: str
    password: str


@dataclass(frozen=True)
class QueryConfig:
    """Default grade query configuration."""

    year: str
    semester: str


@dataclass(frozen=True)
class HTTPConfig:
    """HTTP client configuration."""

    timeout_seconds: float
    retry_attempts: int
    retry_backoff_seconds: float


@dataclass(frozen=True)
class GradesConfig:
    """Grade query behavior configuration."""

    include_details_on_change: bool
    detail_concurrency: int


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """OpenAI-compatible captcha service configuration."""

    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class CaptchaConfig:
    """Captcha recognition configuration."""

    provider: str
    manual_timeout_seconds: int
    openai_compatible: OpenAICompatibleConfig


@dataclass(frozen=True)
class NotifyConfig:
    """Email notification configuration."""

    enabled: bool
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    sender: str
    recipients: tuple[str, ...]


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    retention_days: int


@dataclass(frozen=True)
class OutputConfig:
    """Optional output artifact configuration."""

    save_json: bool
    save_report: bool
    output_dir: str


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from file, environment, and CLI."""

    config_path: Path
    cumt: CUMTConfig
    query: QueryConfig
    http: HTTPConfig
    grades: GradesConfig
    captcha: CaptchaConfig
    notify: NotifyConfig
    logging: LoggingConfig
    output: OutputConfig


@dataclass(frozen=True)
class CourseGrade:
    """Parsed course grade record."""

    course_code: str
    course_name: str
    score: str
    credit: str | None = None
    grade_point: str | None = None
    course_type: str | None = None
    exam_type: str | None = None
    teaching_class_id: str | None = None


@dataclass(frozen=True)
class GradeSnapshotEntry:
    """Minimal grade record stored for change detection."""

    course_code: str
    course_name: str
    score: str


@dataclass(frozen=True)
class GradeChange:
    """Structured difference between two grade snapshots."""

    change_type: Literal["added", "updated", "removed"]
    before: GradeSnapshotEntry | None
    after: GradeSnapshotEntry | None


@dataclass(frozen=True)
class GradeDetailComponent:
    """Parsed score component from a course detail page."""

    name: str
    percentage: str
    score: str


@dataclass(frozen=True)
class GradeDetail:
    """Parsed grade detail for one course."""

    course_code: str
    course_name: str
    components: tuple[GradeDetailComponent, ...]


@dataclass(frozen=True)
class RuntimeState:
    """Minimal runtime state safe to persist between runs."""

    schema_version: int
    session_cookies: dict[str, str]
    session_updated_at: str | None
    last_grade_snapshot: tuple[GradeSnapshotEntry, ...]
    last_successful_query_at: str | None
    last_notified_at: str | None


@dataclass(frozen=True)
class GradeQueryResult:
    """Pure business result for a completed grade query workflow."""

    grades: tuple[CourseGrade, ...]
    snapshot: tuple[GradeSnapshotEntry, ...]
    changes: tuple[GradeChange, ...]
    details: tuple[GradeDetail, ...]
    state: RuntimeState
