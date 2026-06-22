"""Grade service orchestration tests."""

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

import cumt_jwxt_cli.grades.service as service_module
from cumt_jwxt_cli.errors import NotifyError, SnapshotError, StateError
from cumt_jwxt_cli.grades.service import (
    build_grade_query_result,
    is_session_query_failure,
    run_grade_query,
)
from cumt_jwxt_cli.models import (
    AppConfig,
    CaptchaConfig,
    CourseGrade,
    CUMTConfig,
    GradeChange,
    GradeQueryScope,
    GradesConfig,
    GradeSnapshotEntry,
    HTTPConfig,
    LoggingConfig,
    NotifyConfig,
    OpenAICompatibleConfig,
    OutputConfig,
    PerScopeState,
    QueryConfig,
    RuntimeState,
)


def _grade(course_code: str, course_name: str, score: str) -> CourseGrade:
    return CourseGrade(course_code=course_code, course_name=course_name, score=score)


def _entry(course_code: str, course_name: str, score: str) -> GradeSnapshotEntry:
    return GradeSnapshotEntry(
        course_code=course_code, course_name=course_name, score=score
    )


def _scope(year: str = "2024", semester: str = "12") -> GradeQueryScope:
    return GradeQueryScope(year=year, semester=semester)


def _per_scope(
    snapshot: tuple[GradeSnapshotEntry, ...],
    *,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> PerScopeState:
    return PerScopeState(
        snapshot=snapshot,
        last_successful_query_at=last_successful_query_at,
        last_notified_at=last_notified_at,
    )


def _state(
    snapshot: tuple[GradeSnapshotEntry, ...],
    *,
    scope: GradeQueryScope | None = None,
    grade_queries: dict[GradeQueryScope, PerScopeState] | None = None,
    session_cookies: dict[str, str] | None = None,
    session_updated_at: str | None = None,
    last_successful_query_at: str | None = None,
    last_notified_at: str | None = None,
) -> RuntimeState:
    if grade_queries is None:
        grade_queries = {
            _scope() if scope is None else scope: _per_scope(
                snapshot,
                last_successful_query_at=last_successful_query_at,
                last_notified_at=last_notified_at,
            )
        }
    return RuntimeState(
        schema_version=4,
        session_cookies={} if session_cookies is None else session_cookies,
        session_updated_at=session_updated_at,
        grade_queries=grade_queries,
        exam_queries={},
    )


def _app_config(
    config_path: Path,
    *,
    notify_enabled: bool = False,
    year: str = "2024",
    semester: str = "12",
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
        output=OutputConfig(
            save_json=False, save_report=False, save_ics=False, output_dir=""
        ),
    )


class _QueryResponse:
    def __init__(self, payload: object, *, text: str = "") -> None:
        self._payload = payload
        self.text = text

    def json(self) -> object:
        return self._payload


class _QueryClient:
    def __init__(self, payload: object, *, detail_html: str = "") -> None:
        self.payload = payload
        self.detail_html = detail_html
        self.posts: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def post(
        self,
        path: str,
        *,
        data: dict[str, str],
        params: dict[str, str] | None = None,
    ) -> _QueryResponse:
        self.posts.append((path, data, params or {}))
        if path.endswith("cjcx_cxCjxqGjh.html"):
            return _QueryResponse({}, text=self.detail_html)
        return _QueryResponse(self.payload)


def test_build_grade_query_result_creates_snapshot_and_state_from_empty_history() -> (
    None
):
    grades = [
        _grade("B002", "大学英语", "88"),
        _grade("A001", "高等数学", "95"),
    ]

    result = build_grade_query_result(
        grades,
        previous_state=_state((), last_notified_at="2026-05-05T11:55:00+08:00"),
        scope=_scope(),
        queried_at="2026-05-05T12:00:00+08:00",
    )

    grades.append(_grade("C003", "大学物理", "90"))

    assert result.grades == (
        _grade("B002", "大学英语", "88"),
        _grade("A001", "高等数学", "95"),
    )
    assert result.snapshot == (
        _entry("A001", "高等数学", "95"),
        _entry("B002", "大学英语", "88"),
    )
    assert result.changes == (
        GradeChange(
            change_type="added", before=None, after=_entry("A001", "高等数学", "95")
        ),
        GradeChange(
            change_type="added", before=None, after=_entry("B002", "大学英语", "88")
        ),
    )
    assert result.state == RuntimeState(
        schema_version=4,
        session_cookies={},
        session_updated_at=None,
        grade_queries={
            _scope(): _per_scope(
                result.snapshot,
                last_successful_query_at="2026-05-05T12:00:00+08:00",
                last_notified_at="2026-05-05T11:55:00+08:00",
            )
        },
        exam_queries={},
    )
    assert result.details == ()


def test_build_grade_query_result_preserves_compare_snapshots_change_order() -> None:
    previous_state = _state(
        (
            _entry("A001", "高等数学", "95"),
            _entry("B002", "大学英语", "88"),
        )
    )

    result = build_grade_query_result(
        [
            _grade("C003", "大学物理", "91"),
            _grade("B002", "大学英语", "90"),
        ],
        previous_state=previous_state,
        scope=_scope(),
        queried_at="2026-05-05T12:00:00+08:00",
    )

    assert result.changes == (
        GradeChange(
            change_type="removed",
            before=_entry("A001", "高等数学", "95"),
            after=None,
        ),
        GradeChange(
            change_type="added",
            before=None,
            after=_entry("C003", "大学物理", "91"),
        ),
        GradeChange(
            change_type="updated",
            before=_entry("B002", "大学英语", "88"),
            after=_entry("B002", "大学英语", "90"),
        ),
    )
    assert result.state.grade_queries[_scope()].snapshot == (
        _entry("B002", "大学英语", "90"),
        _entry("C003", "大学物理", "91"),
    )


def test_build_grade_query_result_compares_only_current_scope() -> None:
    spring_scope = _scope("2025", "3")
    autumn_scope = _scope("2025", "12")
    previous_state = _state(
        (),
        grade_queries={
            spring_scope: _per_scope((_entry("A001", "高等数学", "95"),)),
            autumn_scope: _per_scope((_entry("B002", "大学英语", "88"),)),
        },
    )

    result = build_grade_query_result(
        [_grade("B002", "大学英语", "88")],
        previous_state=previous_state,
        scope=autumn_scope,
        queried_at="2026-05-05T12:00:00+08:00",
    )

    assert result.changes == ()
    assert result.state.grade_queries[spring_scope].snapshot == (
        _entry("A001", "高等数学", "95"),
    )
    assert result.state.grade_queries[autumn_scope].snapshot == (
        _entry("B002", "大学英语", "88"),
    )


def test_build_grade_query_result_overrides_last_notified_at_when_provided() -> None:
    result = build_grade_query_result(
        [_grade("A001", "高等数学", "95")],
        previous_state=_state((), last_notified_at="2026-05-05T11:55:00+08:00"),
        scope=_scope(),
        queried_at="2026-05-05T12:00:00+08:00",
        notified_at="2026-05-05T12:05:00+08:00",
    )

    assert (
        result.state.grade_queries[_scope()].last_notified_at
        == "2026-05-05T12:05:00+08:00"
    )


def test_build_grade_query_result_propagates_duplicate_snapshot_identity() -> None:
    with pytest.raises(SnapshotError, match="Duplicate snapshot identity"):
        build_grade_query_result(
            [
                _grade("A001", "高等数学", "95"),
                _grade("A001", "高等数学", "90"),
            ],
            previous_state=_state(()),
            scope=_scope(),
            queried_at="2026-05-05T12:00:00+08:00",
        )


def test_build_grade_query_result_rejects_missing_query_timestamp() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(
                (),
                last_successful_query_at="2026-05-05T11:00:00+08:00",
            ),
            scope=_scope(),
            queried_at=None,  # type: ignore[arg-type]
        )


def test_build_grade_query_result_rejects_invalid_timestamp_fields() -> None:
    with pytest.raises(StateError, match="last_successful_query_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(()),
            scope=_scope(),
            queried_at="not-a-timestamp",
        )

    with pytest.raises(StateError, match="last_notified_at"):
        build_grade_query_result(
            [_grade("A001", "高等数学", "95")],
            previous_state=_state(()),
            scope=_scope(),
            queried_at="2026-05-05T12:00:00+08:00",
            notified_at="  ",
        )


def test_run_grade_query_saves_state_after_successful_query(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]})

    result = run_grade_query(
        config,
        client,
        previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
        session_cookies={"JSESSIONID": "existing"},
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert result.changes == (
        GradeChange(
            change_type="added",
            before=None,
            after=_entry("A001", "高等数学", "95"),
        ),
    )
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state_payload["schema_version"] == 4
    assert state_payload["session_cookies"] == {"JSESSIONID": "existing"}
    assert state_payload["grade_queries"]["2024-12"]["snapshot"] == [
        {"course_code": "A001", "course_name": "高等数学", "score": "95"}
    ]


def test_run_grade_query_keeps_semester_histories_isolated(tmp_path) -> None:
    spring_scope = _scope("2025", "3")
    autumn_scope = _scope("2025", "12")
    previous_state = _state(
        (),
        grade_queries={
            spring_scope: _per_scope((_entry("A001", "高等数学", "95"),)),
            autumn_scope: _per_scope((_entry("B002", "大学英语", "88"),)),
        },
    )
    config = _app_config(
        tmp_path / "config.local.json",
        year="2025",
        semester="12",
    )
    client = _QueryClient({"items": [{"kch": "B002", "kcmc": "大学英语", "cj": "88"}]})

    result = run_grade_query(
        config,
        client,
        previous_state=previous_state,
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert result.changes == ()
    assert result.state.grade_queries[spring_scope].snapshot == (
        _entry("A001", "高等数学", "95"),
    )
    state_payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(state_payload["grade_queries"]) == {"2025-3", "2025-12"}
    assert state_payload["grade_queries"]["2025-3"]["snapshot"] == [
        {"course_code": "A001", "course_name": "高等数学", "score": "95"}
    ]
    assert state_payload["grade_queries"]["2025-12"]["snapshot"] == [
        {"course_code": "B002", "course_name": "大学英语", "score": "88"}
    ]


def test_run_grade_query_saves_json_with_stable_schema_in_explicit_output_dir(
    tmp_path,
) -> None:
    output_dir = tmp_path / "artifacts"
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
            save_json=True,
            save_report=False,
            save_ics=False,
            output_dir=str(output_dir),
        ),
    )
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "xf": "4.0",
                    "jd": "4.5",
                    "xfjd": "18.0",
                    "kcxzmc": "必修",
                    "khfsmc": "考试",
                    "jsxm": "张老师",
                    "jxb_id": "JXB-1",
                }
            ]
        },
        detail_html="""
        <span class="red2">高等数学</span>
        <table id="subtab">
          <tbody><tr><td>平时</td><td>30%</td><td>90</td></tr></tbody>
        </table>
        """,
    )

    run_grade_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    payload = json.loads((output_dir / "grades_24sp.json").read_text(encoding="utf-8"))

    assert set(payload) == {"grades", "changes", "details", "summary"}
    assert set(payload["grades"][0]) == {
        "course_code",
        "course_name",
        "score",
        "credit",
        "grade_point",
        "credit_grade_point",
        "course_type",
        "exam_type",
        "teacher_name",
        "teaching_class_id",
    }
    assert set(payload["changes"][0]) == {"change_type", "before", "after"}
    assert payload["changes"][0]["before"] is None
    assert set(payload["changes"][0]["after"]) == {
        "course_code",
        "course_name",
        "score",
    }
    assert set(payload["details"][0]) == {"course_code", "course_name", "components"}
    assert set(payload["details"][0]["components"][0]) == {
        "name",
        "percentage",
        "score",
    }
    assert "session_cookies" not in payload
    assert "session_updated_at" not in payload
    assert "username" not in json.dumps(payload, ensure_ascii=False)
    assert "password" not in json.dumps(payload, ensure_ascii=False)


def test_run_grade_query_uses_explicit_output_dir_for_json_output(
    tmp_path,
) -> None:
    output_dir = tmp_path / "custom-output"
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
            save_json=True,
            save_report=False,
            save_ics=False,
            output_dir=str(output_dir),
        ),
    )
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]})

    run_grade_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert (output_dir / "grades_24sp.json").exists()
    assert not (tmp_path / "output" / "grades_24sp.json").exists()


def test_run_grade_query_fetches_details_for_changed_courses(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                },
                {
                    "kch": "B002",
                    "kcmc": "大学英语",
                    "cj": "88",
                    "jxb_id": "JXB-2",
                },
            ]
        },
        detail_html="""
        <span class="red2">高等数学</span>
        <table id="subtab">
          <tbody><tr><td>平时</td><td>30%</td><td>90</td></tr></tbody>
        </table>
        """,
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state((_entry("B002", "大学英语", "88"),)),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    detail_posts = [
        post for post in client.posts if post[0].endswith("cjcx_cxCjxqGjh.html")
    ]
    assert len(detail_posts) == 1
    assert detail_posts[0][1] == {
        "jxb_id": "JXB-1",
        "xnm": "2024",
        "xqm": "12",
        "kcmc": "高等数学",
    }
    assert detail_posts[0][2]["gnmkdm"] == "N305005"
    assert result.details[0].course_code == "A001"


def test_run_grade_query_skips_details_when_no_changes(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                }
            ]
        }
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state((_entry("A001", "高等数学", "95"),)),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert all(not post[0].endswith("cjcx_cxCjxqGjh.html") for post in client.posts)
    assert result.details == ()


def test_run_grade_query_fetches_details_for_saved_report_without_changes(
    tmp_path,
) -> None:
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
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                }
            ]
        },
        detail_html="""
        <span class="red2">高等数学</span>
        <table id="subtab">
          <tbody><tr><td>期末</td><td>100%</td><td>95</td></tr></tbody>
        </table>
        """,
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state((_entry("A001", "高等数学", "95"),)),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    detail_posts = [
        post for post in client.posts if post[0].endswith("cjcx_cxCjxqGjh.html")
    ]
    assert len(detail_posts) == 1
    assert result.details[0].course_code == "A001"
    assert "成绩构成" in (tmp_path / "output" / "grade_report_24sp.html").read_text(
        encoding="utf-8"
    )


def test_run_grade_query_skips_details_when_disabled(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    config = AppConfig(
        config_path=config.config_path,
        cumt=config.cumt,
        query=config.query,
        http=config.http,
        grades=GradesConfig(include_details_on_change=False, detail_concurrency=3),
        captcha=config.captcha,
        notify=config.notify,
        logging=config.logging,
        output=config.output,
    )
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                }
            ]
        }
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert all(not post[0].endswith("cjcx_cxCjxqGjh.html") for post in client.posts)
    assert result.details == ()


def test_run_grade_query_continues_when_detail_parse_fails(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                }
            ]
        },
        detail_html="<html></html>",
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert len(result.changes) == 1
    assert result.details == ()
    assert (tmp_path / "state.json").exists()


def test_run_grade_query_fetches_details_when_force_email_is_set(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json")
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                }
            ]
        },
        detail_html="""
        <span class="red2">高等数学</span>
        <table id="subtab">
          <tbody><tr><td>期末</td><td>100%</td><td>95</td></tr></tbody>
        </table>
        """,
    )

    result = run_grade_query(
        config,
        client,
        previous_state=_state((_entry("A001", "高等数学", "95"),)),
        force_email=True,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    detail_posts = [
        post for post in client.posts if post[0].endswith("cjcx_cxCjxqGjh.html")
    ]
    assert len(detail_posts) == 1
    assert result.details[0].course_code == "A001"


def test_run_grade_query_uses_readable_term_label_in_email_subject(tmp_path) -> None:
    base_config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    config = AppConfig(
        config_path=base_config.config_path,
        cumt=base_config.cumt,
        query=QueryConfig(year="2025", semester="3"),
        http=base_config.http,
        grades=base_config.grades,
        captcha=base_config.captcha,
        notify=base_config.notify,
        logging=base_config.logging,
        output=base_config.output,
    )
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]})
    sent_subjects: list[str] = []

    def collect_email(*args: object, subject: str, **kwargs: object) -> None:
        sent_subjects.append(subject)

    run_grade_query(
        config,
        client,
        previous_state=_state((_entry("A001", "高等数学", "95"),)),
        force_email=True,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
        send_email_fn=collect_email,
    )

    assert sent_subjects == ["CUMT 成绩报告 2025-2026学年 第一学期"]


def test_run_grade_query_applies_detail_concurrency_limit(
    tmp_path,
    monkeypatch,
) -> None:
    config = _app_config(tmp_path / "config.local.json")
    config = AppConfig(
        config_path=config.config_path,
        cumt=config.cumt,
        query=config.query,
        http=config.http,
        grades=GradesConfig(include_details_on_change=True, detail_concurrency=2),
        captcha=config.captcha,
        notify=config.notify,
        logging=config.logging,
        output=config.output,
    )
    client = _QueryClient(
        {
            "items": [
                {
                    "kch": "A001",
                    "kcmc": "高等数学",
                    "cj": "95",
                    "jxb_id": "JXB-1",
                },
                {
                    "kch": "B002",
                    "kcmc": "大学英语",
                    "cj": "88",
                    "jxb_id": "JXB-2",
                },
                {
                    "kch": "C003",
                    "kcmc": "大学物理",
                    "cj": "90",
                    "jxb_id": "JXB-3",
                },
            ]
        },
        detail_html="""
        <span class="red2">课程</span>
        <table id="subtab">
          <tbody><tr><td>期末</td><td>100%</td><td>95</td></tr></tbody>
        </table>
        """,
    )
    created_workers: list[int] = []

    class FakeExecutor:
        def __init__(self, *, max_workers: int) -> None:
            created_workers.append(max_workers)

        def __enter__(self) -> "FakeExecutor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def map(
            self,
            fn: Callable[[CourseGrade], object],
            items: Iterable[CourseGrade],
        ) -> list[object]:
            return [fn(item) for item in items]

    monkeypatch.setattr(service_module, "ThreadPoolExecutor", FakeExecutor)

    run_grade_query(
        config,
        client,
        previous_state=_state(()),
        force_email=False,
        now_factory=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-07T12:00:00+08:00"
        ),
    )

    assert created_workers == [2]


def test_run_grade_query_does_not_update_state_when_notify_fails(tmp_path) -> None:
    config = _app_config(tmp_path / "config.local.json", notify_enabled=True)
    client = _QueryClient({"items": [{"kch": "A001", "kcmc": "高等数学", "cj": "95"}]})

    def fail_email(*args: object, **kwargs: object) -> None:
        raise NotifyError("boom")

    with pytest.raises(NotifyError, match="boom"):
        run_grade_query(
            config,
            client,
            previous_state=_state((), session_cookies={"JSESSIONID": "existing"}),
            session_cookies={"JSESSIONID": "existing"},
            force_email=False,
            now_factory=lambda: __import__("datetime").datetime.fromisoformat(
                "2026-05-07T12:00:00+08:00"
            ),
            send_email_fn=fail_email,
        )

    assert not (tmp_path / "state.json").exists()


def test_is_session_query_failure_matches_known_session_markers() -> None:
    assert is_session_query_failure(
        __import__("cumt_jwxt_cli.errors").errors.QueryError(
            "JWXT grade list request failed with HTTP 901."
        )
    )
    assert is_session_query_failure(
        __import__("cumt_jwxt_cli.errors").errors.QueryError(
            "JWXT grade list request was redirected with HTTP 302."
        )
    )
    assert is_session_query_failure(
        __import__("cumt_jwxt_cli.errors").errors.QueryError(
            "JWXT grade list response looks like an HTML login page."
        )
    )
    assert not is_session_query_failure(
        __import__("cumt_jwxt_cli.errors").errors.QueryError(
            "JWXT grade list response is not valid JSON."
        )
    )
    assert not is_session_query_failure(
        __import__("cumt_jwxt_cli.errors").errors.QueryError(
            "JWXT request failed after retry attempts."
        )
    )
