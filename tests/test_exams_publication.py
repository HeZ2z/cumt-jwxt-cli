"""Exam publication tests."""

import json
from pathlib import Path

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.exams.publication import (
    PublicationArtifacts,
    build_exams_json_payload,
    build_publication_artifacts,
    maybe_notify,
    save_optional_outputs,
    serialize_exam_change,
    serialize_exam_info,
    serialize_exam_snapshot_entry,
)
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CUMTConfig,
    ExamChange,
    ExamInfo,
    ExamQueryResult,
    ExamSnapshotEntry,
    GradesConfig,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    QueryConfig,
    RuntimeState,
)


def _app_config(
    config_path: Path,
    *,
    notify_enabled: bool = False,
    year: str = "2025",
    semester: str = "3",
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
        captcha=CaptchaConfig(
            provider="openai_compatible",
            manual_timeout_seconds=60,
            openai_compatible=OpenAICompatibleConfig(base_url="", api_key="", model=""),
        ),
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
        output=OutputConfig(save_json=False, save_report=False, output_dir=""),
    )


def _exam(course_code: str, course_name: str, **kw: str | None) -> ExamInfo:
    return ExamInfo(
        course_code=course_code,
        course_name=course_name,
        exam_time=kw.get("exam_time"),
        location=kw.get("location"),
        campus=kw.get("campus"),
        exam_name=kw.get("exam_name"),
        exam_method=kw.get("exam_method"),
    )


def _entry(course_code: str, course_name: str, **kw: str | None) -> ExamSnapshotEntry:
    return ExamSnapshotEntry(
        course_code=course_code,
        course_name=course_name,
        exam_time=kw.get("exam_time"),
        location=kw.get("location"),
        campus=kw.get("campus"),
        exam_name=kw.get("exam_name"),
        exam_method=kw.get("exam_method"),
    )


def _result(
    exams: tuple[ExamInfo, ...] = (),
    changes: tuple[ExamChange, ...] = (),
) -> ExamQueryResult:
    return ExamQueryResult(
        exams=exams,
        snapshot=(),
        changes=changes,
        state=RuntimeState(
            schema_version=4,
            session_cookies={},
            session_updated_at=None,
            grade_queries={},
            exam_queries={},
        ),
    )


class TestBuildPublicationArtifacts:
    def test_builds_text_and_html(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"))
        result = _result(
            exams=(_exam("A001", "高等数学"),),
        )
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        assert "CUMT exams" in artifacts.text_summary
        assert "CUMT 考试报告" in artifacts.html_report


class TestMaybeNotify:
    def test_skips_when_notifications_disabled(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=False)
        result = _result(
            changes=(
                ExamChange(change_type="added", before=None, after=_entry("A", "X")),
            ),
        )
        sent: list[str] = []

        def fake_send(**kwargs: object) -> None:
            sent.append(kwargs.get("subject", ""))

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(text_summary="text", html_report="html"),
            force_email=False,
            send_email=fake_send,
        )

        assert notified_at is None
        assert sent == []

    def test_skips_when_no_changes_and_not_forced(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result()
        sent: list[str] = []

        def fake_send(**kwargs: object) -> None:
            sent.append(kwargs.get("subject", ""))

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(text_summary="text", html_report="html"),
            force_email=False,
            send_email=fake_send,
        )

        assert notified_at is None

    def test_sends_when_changes_exist(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result(
            changes=(
                ExamChange(change_type="added", before=None, after=_entry("A", "X")),
            ),
        )
        sent_subjects: list[str] = []

        def fake_send(*args: object, subject: str, **kwargs: object) -> None:
            sent_subjects.append(subject)

        notified_at = maybe_notify(
            config,
            result,
            PublicationArtifacts(text_summary="text", html_report="html"),
            force_email=False,
            send_email=fake_send,
        )

        assert notified_at is not None
        assert sent_subjects == ["CUMT 考试报告 2025-2026 第一学期"]

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
            PublicationArtifacts(text_summary="text", html_report="html"),
            force_email=True,
            send_email=fake_send,
        )

        assert notified_at is not None
        assert sent == 1

    def test_raises_when_send_fails(self) -> None:
        config = _app_config(Path("/tmp/test/config.local.json"), notify_enabled=True)
        result = _result(
            changes=(
                ExamChange(change_type="added", before=None, after=_entry("A", "X")),
            ),
        )

        def failing_send(*args: object, **kwargs: object) -> None:
            raise NotifyError("SMTP server not reachable")

        with pytest.raises(NotifyError, match="SMTP"):
            maybe_notify(
                config,
                result,
                PublicationArtifacts(text_summary="text", html_report="html"),
                force_email=False,
                send_email=failing_send,
            )


class TestSaveOptionalOutputs:
    def test_saves_nothing_when_disabled(self, tmp_path: Path) -> None:
        config = _app_config(tmp_path / "config.local.json")
        result = _result(exams=(_exam("A001", "高数"),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)
        assert not list(tmp_path.iterdir())

    def test_saves_json(self, tmp_path: Path) -> None:
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
            output=OutputConfig(save_json=True, save_report=False, output_dir=""),
        )
        result = _result(exams=(_exam("A001", "高数"),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)

        payload = json.loads(
            (tmp_path / "output" / "exams.json").read_text(encoding="utf-8")
        )
        assert set(payload) == {"exams", "changes", "summary"}
        assert "session_cookies" not in payload
        assert "username" not in json.dumps(payload)

    def test_saves_report(self, tmp_path: Path) -> None:
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
            output=OutputConfig(save_json=False, save_report=True, output_dir=""),
        )
        result = _result(exams=(_exam("A001", "高数"),))
        artifacts = build_publication_artifacts(
            config, result, queried_at="2026-06-01T12:00:00"
        )

        save_optional_outputs(config, result, artifacts)

        report = (tmp_path / "output" / "exam_report.html").read_text(encoding="utf-8")
        assert "CUMT 考试报告" in report


class TestSerializers:
    def test_serialize_exam_info(self) -> None:
        exam = _exam(
            "A001",
            "高数",
            exam_time="2026-06-01(08:00)",
            location="博1-A101",
            campus="南湖校区",
            exam_name="期末考试",
            exam_method="闭卷",
        )
        data = serialize_exam_info(exam)
        assert data["course_code"] == "A001"
        assert data["exam_method"] == "闭卷"

    def test_serialize_exam_change_added(self) -> None:
        change = ExamChange(
            change_type="added",
            before=None,
            after=_entry("A001", "高数"),
        )
        data = serialize_exam_change(change)
        assert data["change_type"] == "added"
        assert data["before"] is None
        assert data["after"] is not None

    def test_serialize_exam_snapshot_entry(self) -> None:
        entry = _entry("A001", "高数", exam_time="2026-06-01(08:00)")
        data = serialize_exam_snapshot_entry(entry)
        assert data["course_code"] == "A001"
        assert data["exam_time"] == "2026-06-01(08:00)"

    def test_build_exams_json_payload_structure(self) -> None:
        result = _result(
            exams=(_exam("A001", "高数"),),
            changes=(
                ExamChange(
                    change_type="added",
                    before=None,
                    after=_entry("A001", "高数"),
                ),
            ),
        )
        payload = build_exams_json_payload(result, "summary text")
        assert set(payload) == {"exams", "changes", "summary"}
        assert payload["summary"] == "summary text"
