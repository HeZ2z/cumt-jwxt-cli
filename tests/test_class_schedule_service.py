"""Class timetable service orchestration tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.class_schedule.query_fetch import ClassScheduleFilters
from cumt_jwxt_cli.class_schedule.service import run_class_schedule_query
from cumt_jwxt_cli.errors import ConfigError


def _config() -> SimpleNamespace:
    return SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))


class _FakeResponse:
    def __init__(self, json_data: object, status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def json(self) -> object:
        return self._json_data


class _RecordingClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def _entry_payload(**overrides: object) -> dict[str, object]:
    entry = {
        "tjkbzdm": "T1",
        "tjkbzxsdm": "A1",
        "tjkbmc": "课表1",
        "bh_id": "0810-202301",
        "bh": "202301",
        "bjmc": "计算机2023-1",
        "zymc": "计算机科学与技术",
        "njmc": "2023",
        "jgmc": "计算机学院",
        "xqmc": "南湖校区",
        "xkrs": "40",
    }
    entry.update(overrides)
    return entry


def _lesson(**overrides: object) -> dict[str, object]:
    lesson = {
        "kch": "M1",
        "kcmc": "高等数学",
        "xm": "张三",
        "zcd": "1-8周",
        "jcs": "1-2",
        "xqj": 1,
        "cdmc": "博1-A203",
    }
    lesson.update(overrides)
    return lesson


def test_list_only_returns_entries_without_timetable_request() -> None:
    list_payload = {
        "items": [_entry_payload(), _entry_payload(bh_id="2", bjmc="另一个班")],
        "totalResult": 2,
    }
    client = _RecordingClient(_FakeResponse(list_payload))

    result = run_class_schedule_query(
        _config(), client, ClassScheduleFilters(list_only=True, grade="2023")
    )

    assert result.entry is None
    assert result.lessons == ()
    assert result.total == 2
    assert len(result.entries) == 2
    assert len(client.calls) == 1


def test_requires_a_narrowing_filter_before_fetching() -> None:
    client = _RecordingClient()

    with pytest.raises(ConfigError, match="--class"):
        run_class_schedule_query(_config(), client, ClassScheduleFilters())

    assert client.calls == []


def test_list_only_applies_class_filter() -> None:
    list_payload = {
        "items": [_entry_payload(), _entry_payload(bh_id="2", bjmc="另一个班")],
        "totalResult": 2,
    }
    client = _RecordingClient(_FakeResponse(list_payload))

    result = run_class_schedule_query(
        _config(),
        client,
        ClassScheduleFilters(list_only=True, class_query="另一个"),
    )

    assert result.total == 1
    assert result.entries[0].class_name == "另一个班"


def test_unique_match_is_selected_automatically() -> None:
    list_payload = {"items": [_entry_payload()], "totalResult": 1}
    timetable_payload = {"kbList": [_lesson()]}
    client = _RecordingClient(
        _FakeResponse(list_payload),
        _FakeResponse(timetable_payload),
    )

    result = run_class_schedule_query(
        _config(), client, ClassScheduleFilters(grade="2023")
    )

    assert result.entry is not None
    assert result.entry.class_id == "0810-202301"
    assert len(result.lessons) == 1
    assert client.calls[1]["path"] == "/kbdy/bjkbdy_cxBjKb.html"


def test_multiple_matches_without_class_raise_config_error() -> None:
    list_payload = {
        "items": [_entry_payload(), _entry_payload(bh_id="2", bjmc="另一个班")],
        "totalResult": 2,
    }
    client = _RecordingClient(_FakeResponse(list_payload))

    with pytest.raises(ConfigError, match="--class"):
        run_class_schedule_query(_config(), client, ClassScheduleFilters(grade="2023"))

    assert len(client.calls) == 1


def test_no_matches_raise_config_error() -> None:
    client = _RecordingClient(
        _FakeResponse({"items": [], "totalResult": 0}),
    )

    with pytest.raises(ConfigError, match="未找到"):
        run_class_schedule_query(
            _config(), client, ClassScheduleFilters(class_query="不存在")
        )


def test_week_filter_keeps_matching_lessons() -> None:
    list_payload = {"items": [_entry_payload()], "totalResult": 1}
    timetable_payload = {
        "kbList": [
            _lesson(kch="M1", kcmc="课1", zcd="1-2周"),
            _lesson(kch="M2", kcmc="课2", zcd="5-6周"),
        ]
    }
    client = _RecordingClient(
        _FakeResponse(list_payload),
        _FakeResponse(timetable_payload),
    )

    result = run_class_schedule_query(
        _config(), client, ClassScheduleFilters(grade="2023", week=2)
    )

    assert [lesson.course_code for lesson in result.lessons] == ["M1"]


def test_week_filter_without_lessons_returns_empty() -> None:
    list_payload = {"items": [_entry_payload()], "totalResult": 1}
    timetable_payload = {"kbList": [_lesson(zcd="1-2周")]}
    client = _RecordingClient(
        _FakeResponse(list_payload),
        _FakeResponse(timetable_payload),
    )

    result = run_class_schedule_query(
        _config(), client, ClassScheduleFilters(grade="2023", week=10)
    )

    assert result.lessons == ()
    assert result.week == 10


def test_lessons_are_sorted_by_weekday_period_and_course() -> None:
    list_payload = {"items": [_entry_payload()], "totalResult": 1}
    timetable_payload = {
        "kbList": [
            _lesson(kch="M3", kcmc="周三", xqj=3, jcs="1-2"),
            _lesson(kch="M2", kcmc="周一后", xqj=1, jcs="5-6"),
            _lesson(kch="M1", kcmc="周一前", xqj=1, jcs="1-2"),
        ]
    }
    client = _RecordingClient(
        _FakeResponse(list_payload),
        _FakeResponse(timetable_payload),
    )

    result = run_class_schedule_query(
        _config(), client, ClassScheduleFilters(grade="2023")
    )

    assert [lesson.course_code for lesson in result.lessons] == ["M1", "M2", "M3"]
