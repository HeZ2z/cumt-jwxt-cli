"""Core data models."""

from dataclasses import dataclass, field
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
class CaptchaConfig:
    """Captcha recognition configuration."""

    manual_timeout_seconds: int


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
    sender_name: str = ""


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    retention_days: int


@dataclass(frozen=True)
class OutputConfig:
    """Optional output artifact configuration."""

    save_json: bool
    save_report: bool
    save_ics: bool
    output_dir: str

    def resolve_dir(self, config_path: Path) -> Path:
        """Resolve the output directory using the configured fallback rule."""

        if self.output_dir:
            return Path(self.output_dir).expanduser()
        return config_path.parent / "output"


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
    credit_grade_point: str | None = None
    course_type: str | None = None
    exam_type: str | None = None
    teacher_name: str | None = None
    teaching_class_id: str | None = None


@dataclass(frozen=True)
class GradeSnapshotEntry:
    """Minimal grade record stored for change detection."""

    course_code: str
    course_name: str
    score: str


@dataclass(frozen=True)
class GradeQueryScope:
    """Identity of one independent grade query history."""

    year: str
    semester: str


@dataclass(frozen=True)
class PerScopeState:
    """Persisted grade state for one query scope."""

    snapshot: tuple[GradeSnapshotEntry, ...]
    last_successful_query_at: str | None
    last_notified_at: str | None


@dataclass(frozen=True)
class ExamSnapshotEntry:
    """Minimal exam record stored for change detection."""

    course_code: str
    course_name: str
    exam_time: str | None
    location: str | None
    campus: str | None
    exam_name: str | None
    exam_method: str | None


@dataclass(frozen=True)
class ExamScopeState:
    """Persisted exam state for one query scope."""

    snapshot: tuple[ExamSnapshotEntry, ...]
    last_successful_query_at: str | None
    last_notified_at: str | None


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
class PeriodTime:
    """Start/end clock time for one class period."""

    period: str
    start: str
    end: str
    section: str | None = None


@dataclass(frozen=True)
class ScheduleSlot:
    """One meeting slot of a scheduled course."""

    weekday: int
    periods: str
    weeks: tuple[int, ...]
    location: str | None


@dataclass(frozen=True)
class ScheduleLesson:
    """Parsed personal schedule lesson record.

    One kbList row maps to one lesson carrying exactly one slot.
    """

    course_code: str
    course_name: str
    teaching_class: str | None
    teacher: str | None
    credits: str | None
    course_type: str | None
    slots: tuple[ScheduleSlot, ...]


@dataclass(frozen=True)
class ScheduleUnscheduledCourse:
    """Parsed sjkList practice/unscheduled course record."""

    course_name: str
    teacher: str | None
    week_range: str | None
    credits: str | None


@dataclass(frozen=True)
class ScheduleSnapshotEntry:
    """Minimal schedule record stored for change detection."""

    course_code: str
    course_name: str
    teaching_class: str | None
    teacher: str | None
    slots: tuple[ScheduleSlot, ...]


@dataclass(frozen=True)
class ScheduleScopeState:
    """Persisted schedule state for one query scope."""

    snapshot: tuple[ScheduleSnapshotEntry, ...]
    last_successful_query_at: str | None
    last_notified_at: str | None


@dataclass(frozen=True)
class RuntimeState:
    """Minimal runtime state safe to persist between runs."""

    schema_version: int
    session_cookies: dict[str, str]
    session_updated_at: str | None
    grade_queries: dict[GradeQueryScope, PerScopeState]
    exam_queries: dict[GradeQueryScope, ExamScopeState]
    schedule_queries: dict[GradeQueryScope, ScheduleScopeState] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ExamInfo:
    """Parsed exam schedule record."""

    course_code: str
    course_name: str
    exam_time: str | None = None
    location: str | None = None
    campus: str | None = None
    exam_name: str | None = None
    exam_method: str | None = None
    class_schedule: str | None = None
    teacher_info: str | None = None
    credit: str | None = None


@dataclass(frozen=True)
class ExamChange:
    """Structured difference between two exam snapshots."""

    change_type: Literal["added", "updated", "removed"]
    before: ExamSnapshotEntry | None
    after: ExamSnapshotEntry | None


@dataclass(frozen=True)
class ExamQueryResult:
    """Pure business result for a completed exam query workflow."""

    exams: tuple[ExamInfo, ...]
    snapshot: tuple[ExamSnapshotEntry, ...]
    changes: tuple[ExamChange, ...]
    state: RuntimeState


@dataclass(frozen=True)
class GradeQueryResult:
    """Pure business result for a completed grade query workflow."""

    grades: tuple[CourseGrade, ...]
    snapshot: tuple[GradeSnapshotEntry, ...]
    changes: tuple[GradeChange, ...]
    details: tuple[GradeDetail, ...]
    state: RuntimeState


@dataclass(frozen=True)
class ScheduleListData:
    """Parsed schedule payload containing scheduled and unscheduled courses."""

    lessons: tuple[ScheduleLesson, ...]
    unscheduled: tuple[ScheduleUnscheduledCourse, ...]


@dataclass(frozen=True)
class ScheduleChange:
    """Structured difference between two schedule snapshots."""

    change_type: Literal["added", "removed", "updated"]
    before: ScheduleSnapshotEntry | None
    after: ScheduleSnapshotEntry | None


@dataclass(frozen=True)
class ScheduleQueryResult:
    """Pure business result for a completed schedule query workflow."""

    lessons: tuple[ScheduleLesson, ...]
    unscheduled: tuple[ScheduleUnscheduledCourse, ...]
    snapshot: tuple[ScheduleSnapshotEntry, ...]
    changes: tuple[ScheduleChange, ...]
    state: RuntimeState
    period_times: tuple[PeriodTime, ...] = ()
