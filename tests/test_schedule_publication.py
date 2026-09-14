"""Personal schedule publication tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OutputConfig,
    PeriodTime,
    QueryConfig,
    RuntimeState,
    ScheduleChange,
    ScheduleLesson,
    ScheduleQueryResult,
    ScheduleSlot,
    ScheduleSnapshotEntry,
    ScheduleUnscheduledCourse,
)
from cumt_jwxt_cli.schedule.publication import (
    PublicationArtifacts,
    build_publication_artifacts,
    build_schedules_json_payload,
    maybe_notify,
    save_optional_outputs,
    serialize_schedule_change,
    serialize_schedule_lesson,
    serialize_schedule_slot,
    serialize_schedule_snapshot_entry,
    serialize_schedule_unscheduled_course,
)

_PERIOD_TIMES = (
    PeriodTime(period="1", start="08:00", end="08:50"),
    PeriodTime(period="2", start="08:55", end="09:45"),
)
_WEEK_DATES = {1: __import__("datetime").date(2025, 9, 1)}


def _app_config(
    config_path: Path,
    *,
    notify_enabled: bool = False,
    year: str = "2025",
    semester: str = "3",
    save_ics: bool = False,
) -> AppConfig:
    return AppConfig(
        config_path=config_path,
        cumt=CUMTConfig(username="student", password="secret"),
        query=QueryConfig(year=year, semester=semester),
        http=HTTPConfig(
            timeout_seconds=30.0,
            retry_attempts=2,
            retry_backoff_seconds=1.5,
        ),
        grades=GradesConfig(include_details_on_change=True, detail_concurrency=3),
        captcha=CaptchaConfig(manual_timeout_seconds=60),
        notify=NotifyConfig(
            enabled=notify_enabled,
            smtp_host="smtp.example.test" if notify_enabled else "",
            smtp_port=465,
            username="sender-user" if notify_enabled else "",
            password="sender-password" if notify_enabled else "",
            sender="sender@example.test" if notify_enabled else "",
            recipients=("user@example.test",) if notify_enabled else (),
        ),
        logging=LoggingConfig(retention_days=14),
        output=OutputConfig(
            save_json=False,
            save_report=False,
            save_ics=save_ics,
            output_dir="",
        ),
    )


def _slot(
    weekday: int = 1,
    periods: str = "1-2",
    weeks: tuple[int, ...] = (1,),
    location: str | None = "教一A101",
) -> ScheduleSlot:
    return ScheduleSlot(
        weekday=weekday, periods=periods, weeks=weeks, location=location
    )


def _lesson(course_code: str = "A001", course_name: str = "高等数学") -> ScheduleLesson:
    return ScheduleLesson(
        course_code=course_code,
        course_name=course_name,
        teaching_class="01班",
        teacher="张三",
        credits="5.0",
        course_type="必修",
        slots=(_slot(),),
    )


def _entry(
    course_code: str = "A001", course_name: str = "高等数学"
) -> ScheduleSnapshotEntry:
    return ScheduleSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        teaching_class="01班",
        teacher="张三",
        slots=(_slot(),),
    )


def _result(
    lessons: tuple[ScheduleLesson, ...] = (),
    unscheduled: tuple[ScheduleUnscheduledCourse, ...] = (),
    changes: tuple[ScheduleChange, ...] = (),
) -> ScheduleQueryResult:
    return ScheduleQueryResult(
        lessons=lessons,
        unscheduled=unscheduled,
        snapshot=(),
        changes=changes,
        state=RuntimeState(
            schema_version=5,
            session_cookies={},
            session_updated_at=None,
            grade_queries={},
            exam_queries={},
        ),
    )


class TestBuildPublicationArtifacts:
    def test_builds_text_html_and_ics(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"))
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config,
            result,
            queried_at="2026-06-01T12:00:00",
            period_times=_PERIOD_TIMES,
            week_dates=_WEEK_DATES,
        )

        assert "CUMT 课表" in artifacts.text_summary
        assert "CUMT 个人课表报告" in artifacts.html_report
        assert "周一 1-2节 08:00-09:45" in artifacts.text_summary
        assert "周一 1-2节 08:00-09:45" in artifacts.html_report
        assert "BEGIN:VCALENDAR" in artifacts.ics_content
        assert "END:VCALENDAR" in artifacts.ics_content
        assert "BEGIN:VEVENT" in artifacts.ics_content


class TestMaybeNotify:
    def test_skips_when_notifications_disabled(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=False)
        result = _result(
            changes=(ScheduleChange(change_type="added", before=None, after=_entry()),),
        )
        sent: list[str] = []

        def fake_send(**kwargs: object) -> None:
            sent.append(str(kwargs.get("subject", "")))

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(
                text_summary="text", html_report="html", ics_content="ics"
            ),
            force_email=False,
            send_email_fn=fake_send,
        )

        assert notified_at is None
        assert sent == []

    def test_skips_when_no_changes_and_not_forced(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result()
        sent: list[str] = []

        def fake_send(**kwargs: object) -> None:
            sent.append(str(kwargs.get("subject", "")))

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(
                text_summary="text", html_report="html", ics_content="ics"
            ),
            force_email=False,
            send_email_fn=fake_send,
        )

        assert notified_at is None

    def test_sends_when_changes_exist(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result(
            changes=(ScheduleChange(change_type="added", before=None, after=_entry()),),
        )
        sent_subjects: list[str] = []

        def fake_send(*args: object, subject: str, **kwargs: object) -> None:
            sent_subjects.append(subject)

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(
                text_summary="text", html_report="html", ics_content="ics"
            ),
            force_email=False,
            send_email_fn=fake_send,
        )

        assert notified_at is not None
        assert sent_subjects == ["CUMT 课表报告 2025-2026 第一学期"]

    def test_sends_when_forced(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result()
        sent = 0

        def fake_send(*args: object, **kwargs: object) -> None:
            nonlocal sent
            sent += 1

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(
                text_summary="text", html_report="html", ics_content="ics"
            ),
            force_email=True,
            send_email_fn=fake_send,
        )

        assert notified_at is not None
        assert sent == 1

    def test_sends_ics_attachment(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result(
            changes=(ScheduleChange(change_type="added", before=None, after=_entry()),),
        )
        captured_attachments: list[tuple[str, bytes, str]] = []

        def capturing_send(
            *args: object,
            attachments: list[tuple[str, bytes, str]] | None = None,
            **kwargs: object,
        ) -> None:
            if attachments:
                captured_attachments.extend(attachments)

        maybe_notify(
            config,
            result,
            PublicationArtifacts(
                text_summary="text", html_report="html", ics_content="BEGIN:VCALENDAR"
            ),
            force_email=False,
            send_email_fn=capturing_send,
        )

        assert captured_attachments == [
            ("schedule_25fa.ics", b"BEGIN:VCALENDAR", "text/calendar")
        ]

    def test_raises_when_send_fails(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result(
            changes=(ScheduleChange(change_type="added", before=None, after=_entry()),),
        )

        def failing_send(*args: object, **kwargs: object) -> None:
            raise NotifyError("SMTP server not reachable")

        with pytest.raises(NotifyError, match="SMTP"):
            maybe_notify(
                config,
                result,
                PublicationArtifacts(
                    text_summary="text", html_report="html", ics_content="ics"
                ),
                force_email=False,
                send_email_fn=failing_send,
            )


class TestSaveOptionalOutputs:
    def test_saves_nothing_when_disabled(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json")
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)
        assert not list(tmp_path.iterdir())

    def test_saves_json_with_suffix(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json")
        config = AppConfig(
            config_path=config.config_path,
            cumt=config.cumt,
            query=config.query,
            http=config.http,
            grades=config.grades,
            captcha=config.captcha,
            notify=config.notify,
            logging=config.logging,
            output=OutputConfig(
                save_json=True, save_report=False, save_ics=False, output_dir=""
            ),
        )
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)

        payload = json.loads(
            (tmp_path / "output" / "schedules_25fa.json").read_text(encoding="utf-8")
        )
        assert set(payload) == {"lessons", "unscheduled", "changes", "summary"}
        assert "session_cookies" not in payload
        assert "username" not in json.dumps(payload)

    def test_saves_report_with_suffix(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json")
        config = AppConfig(
            config_path=config.config_path,
            cumt=config.cumt,
            query=config.query,
            http=config.http,
            grades=config.grades,
            captcha=config.captcha,
            notify=config.notify,
            logging=config.logging,
            output=OutputConfig(
                save_json=False, save_report=True, save_ics=False, output_dir=""
            ),
        )
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)

        report = (tmp_path / "output" / "schedule_report_25fa.html").read_text(
            encoding="utf-8"
        )
        assert "CUMT 个人课表报告" in report

    def test_saves_ics(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json", save_ics=True)
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config,
            result,
            queried_at="2026-06-01T12:00:00",
            period_times=_PERIOD_TIMES,
            week_dates=_WEEK_DATES,
        )

        save_optional_outputs(config, result, artifacts)

        ics = (tmp_path / "output" / "schedule_25fa.ics").read_text(
            encoding="utf-8", newline=""
        )
        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics

    def test_saves_ics_preserves_crlf_line_endings(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json", save_ics=True)
        result = _result(lessons=(_lesson(),))
        artifacts = build_publication_artifacts(
            config,
            result,
            queried_at="2026-06-01T12:00:00",
            period_times=_PERIOD_TIMES,
            week_dates=_WEEK_DATES,
        )
        assert "\r\n" in artifacts.ics_content

        save_optional_outputs(config, result, artifacts)

        ics = (tmp_path / "output" / "schedule_25fa.ics").read_text(
            encoding="utf-8", newline=""
        )
        # Default newline translation turned icalendar's CRLF into CRCRLF.
        assert "\r\r\n" not in ics
        assert ics == artifacts.ics_content


class TestSerializers:
    def test_serialize_schedule_lesson(self) -> None:
        data = serialize_schedule_lesson(_lesson())
        assert data["course_code"] == "A001"
        assert data["teacher"] == "张三"
        assert data["slots"][0]["periods"] == "1-2"

    def test_serialize_schedule_unscheduled_course(self) -> None:
        course = ScheduleUnscheduledCourse(
            course_name="实践课", teacher="李四", week_range="1-4", credits="1.0"
        )
        data = serialize_schedule_unscheduled_course(course)
        assert data == {
            "course_name": "实践课",
            "teacher": "李四",
            "week_range": "1-4",
            "credits": "1.0",
        }

    def test_serialize_schedule_change_added(self) -> None:
        change = ScheduleChange(change_type="added", before=None, after=_entry())
        data = serialize_schedule_change(change)
        assert data["change_type"] == "added"
        assert data["before"] is None
        assert data["after"] is not None

    def test_serialize_schedule_snapshot_entry(self) -> None:
        data = serialize_schedule_snapshot_entry(_entry())
        assert data["course_code"] == "A001"
        assert data["slots"] == [
            {
                "weekday": 1,
                "periods": "1-2",
                "weeks": [1],
                "location": "教一A101",
            }
        ]

    def test_serialize_schedule_slot(self) -> None:
        data = serialize_schedule_slot(_slot())
        assert data["weekday"] == 1
        assert data["weeks"] == [1]

    def test_build_schedules_json_payload_structure(self) -> None:
        result = _result(
            lessons=(_lesson(),),
            unscheduled=(
                ScheduleUnscheduledCourse(
                    course_name="实践课",
                    teacher=None,
                    week_range=None,
                    credits=None,
                ),
            ),
            changes=(ScheduleChange(change_type="added", before=None, after=_entry()),),
        )
        payload = build_schedules_json_payload(result, "summary text")
        assert set(payload) == {"lessons", "unscheduled", "changes", "summary"}
        assert payload["summary"] == "summary text"
