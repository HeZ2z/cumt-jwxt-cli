"""Class timetable query fetch and parsing tests."""

from types import SimpleNamespace

import pytest

from cumt_jwxt_cli.class_schedule.query_fetch import (
    ClassScheduleFilters,
    build_list_data,
    is_class_schedule_session_query_failure,
    match_class_schedules,
    parse_class_timetable,
    query_class_schedule_list,
    query_class_timetable,
)
from cumt_jwxt_cli.classrooms.query_fetch import CAMPUS_IDS
from cumt_jwxt_cli.errors import ParseError, QueryError, SessionExpiredError
from cumt_jwxt_cli.models import ClassScheduleEntry


def _config(**overrides: object) -> SimpleNamespace:
    base = SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class _FakeResponse:
    def __init__(
        self,
        json_data: object = None,
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self) -> object:
        return self._json_data


class _RecordingClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, path: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"path": path, **kwargs})
        return self._responses.pop(0)


def _entry(**overrides: object) -> ClassScheduleEntry:
    values: dict[str, object] = {
        "schedule_code": "T1",
        "schedule_aux": "A1",
        "schedule_name": "课表1",
        "class_id": "0810-202301",
        "class_code": "202301",
        "class_name": "计算机2023-1",
        "major_name": "计算机科学与技术",
        "grade_name": "2023",
        "college_name": "计算机学院",
        "campus": "南湖校区",
        "student_count": "40",
        "campus_id": "2",
        "grade_id": "2023",
        "major_id": "0810",
    }
    values.update(overrides)
    return ClassScheduleEntry(**values)  # type: ignore[arg-type]


def test_build_list_data_maps_filters() -> None:
    filters = ClassScheduleFilters(
        campus="nanhu", grade="2023", college="08", major="0810"
    )

    data = build_list_data(_config(), filters)

    assert data["xnm"] == "2026"
    assert data["xqm"] == "3"
    assert data["xqh_id"] == CAMPUS_IDS["nanhu"]
    assert data["njdm_id"] == "2023"
    assert data["jg_id"] == "08"
    assert data["zyh_id"] == "0810"
    assert data["bh_id"] == ""


def test_build_list_data_defaults_empty_campus() -> None:
    data = build_list_data(_config(), ClassScheduleFilters())

    assert data["xqh_id"] == ""
    assert data["njdm_id"] == ""
    assert data["bh_id"] == ""


def test_build_list_data_sends_code_query_to_bh_id_filter() -> None:
    data = build_list_data(_config(), ClassScheduleFilters(class_query="231081001"))
    assert data["bh_id"] == "231081001"


def test_build_list_data_does_not_send_name_query_to_bh_id_filter() -> None:
    data = build_list_data(_config(), ClassScheduleFilters(class_query="计算机2023"))
    assert data["bh_id"] == ""


def test_query_class_schedule_list_parses_entries() -> None:
    payload = {
        "items": [
            {
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
                "xqh_id": "2",
                "njdm_id": "2023",
                "zyh_id": "0810",
            }
        ],
        "totalResult": 1,
    }
    client = _RecordingClient(_FakeResponse(json_data=payload))

    entries = query_class_schedule_list(_config(), client, ClassScheduleFilters())

    assert entries == (_entry(),)
    assert client.calls[0]["path"] == "/kbdy/bjkbdy_cxBjkbdyTjkbList.html"
    assert client.calls[0]["data"]["queryModel.showCount"] == "100"
    assert client.calls[0]["data"]["queryModel.currentPage"] == "1"


def test_query_class_schedule_list_walks_pages_until_total() -> None:
    first_page = [{"bh": f"{index}", "bjmc": f"班级{index}"} for index in range(100)]
    second_page = [
        {"bh": f"{index}", "bjmc": f"班级{index}"} for index in range(100, 150)
    ]
    client = _RecordingClient(
        _FakeResponse(json_data={"items": first_page, "totalResult": 150}),
        _FakeResponse(json_data={"items": second_page, "totalResult": 150}),
    )

    entries = query_class_schedule_list(_config(), client, ClassScheduleFilters())

    assert len(entries) == 150
    assert [call["data"]["queryModel.currentPage"] for call in client.calls] == [
        "1",
        "2",
    ]


def test_query_class_schedule_list_stops_at_total_result() -> None:
    page = [{"bh": f"{index}", "bjmc": f"班级{index}"} for index in range(100)]
    client = _RecordingClient(
        _FakeResponse(json_data={"items": page, "totalResult": 100}),
    )

    entries = query_class_schedule_list(_config(), client, ClassScheduleFilters())

    assert len(entries) == 100
    assert len(client.calls) == 1


def test_query_class_schedule_list_rejects_truncation() -> None:
    page = [{"bh": f"{index}", "bjmc": f"班级{index}"} for index in range(100)]
    responses = tuple(
        _FakeResponse(json_data={"items": page, "totalResult": 1000}) for _ in range(5)
    )
    client = _RecordingClient(*responses)

    with pytest.raises(QueryError, match="ended early"):
        query_class_schedule_list(_config(), client, ClassScheduleFilters())


@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(status_code=901),
        _FakeResponse(status_code=302),
        _FakeResponse(content_type="text/html"),
    ],
)
def test_query_class_schedule_list_raises_on_expired_session(
    response: _FakeResponse,
) -> None:
    client = _RecordingClient(response)

    with pytest.raises(SessionExpiredError):
        query_class_schedule_list(_config(), client, ClassScheduleFilters())


def test_query_class_schedule_list_raises_on_911() -> None:
    client = _RecordingClient(_FakeResponse(status_code=911))

    with pytest.raises(QueryError, match="911"):
        query_class_schedule_list(_config(), client, ClassScheduleFilters())


def test_query_class_schedule_list_raises_on_invalid_payload() -> None:
    client = _RecordingClient(_FakeResponse(json_data={"rows": []}))

    with pytest.raises(ParseError, match="items"):
        query_class_schedule_list(_config(), client, ClassScheduleFilters())


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("0810-202301", ("0810-202301",)),
        ("202301", ("0810-202301",)),
        ("计算机2023-1", ("0810-202301",)),
        ("计算机2023", ("0810-202301", "0910-202302")),
        ("课表2", ("0910-202302",)),
    ],
)
def test_match_class_schedules_exact_then_substring(
    query: str, expected: tuple[str, ...]
) -> None:
    entries = (
        _entry(),
        _entry(
            schedule_name="课表2",
            class_id="0910-202302",
            class_code="202302",
            class_name="计算机2023-2",
            major_id="0910",
        ),
    )

    matches = match_class_schedules(entries, query)

    assert tuple(entry.class_id for entry in matches) == expected


def test_match_class_schedules_without_query_returns_all() -> None:
    entries = (_entry(),)

    assert match_class_schedules(entries, None) == entries


def test_query_class_timetable_builds_form_and_parses_lessons() -> None:
    payload = {
        "kbList": [
            {
                "kch": "M123",
                "kcmc": "高等数学",
                "xm": "张三",
                "zcd": "1-8周,10-16周",
                "jcs": "1-2",
                "xqj": "1",
                "cdmc": "博1-A203",
                "jxbmc": "数学01班",
                "xf": "4",
                "kcxzjc": "必修",
            }
        ]
    }
    client = _RecordingClient(_FakeResponse(json_data=payload))

    lessons = query_class_timetable(_config(), client, _entry())

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.course_code == "M123"
    assert lesson.course_name == "高等数学"
    assert lesson.teacher == "张三"
    assert lesson.course_type == "必修"
    assert lesson.slots[0].weekday == 1
    assert lesson.slots[0].periods == "1-2"
    assert lesson.slots[0].weeks == tuple(range(1, 9)) + tuple(range(10, 17))
    assert lesson.slots[0].location == "博1-A203"
    assert client.calls[0]["path"] == "/kbdy/bjkbdy_cxBjKb.html"
    assert client.calls[0]["data"]["tjkbzdm"] == "T1"
    assert client.calls[0]["data"]["bh_id"] == "0810-202301"


@pytest.mark.parametrize(
    ("zcd", "expected"),
    [
        ("第1周", (1,)),
        ("1-4周", (1, 2, 3, 4)),
        ("1-6周(单)", (1, 3, 5)),
        ("1-6周(双)", (2, 4, 6)),
    ],
)
def test_parse_class_timetable_week_variants(
    zcd: str, expected: tuple[int, ...]
) -> None:
    payload = {
        "kbList": [{"kch": "M1", "kcmc": "课", "xqj": 2, "zcd": zcd, "jcs": "1-2"}]
    }

    lessons = parse_class_timetable(payload)

    assert lessons[0].slots[0].weeks == expected


def test_parse_class_timetable_allows_missing_optional_fields() -> None:
    payload = {
        "kbList": [
            {
                "kch": "M1",
                "kcmc": "课",
                "xqj": 2,
                "zcd": "1周",
                "jcs": "3-4",
                "cdmc": "--",
            }
        ]
    }

    lesson = parse_class_timetable(payload)[0]

    assert lesson.teacher is None
    assert lesson.credits is None
    assert lesson.slots[0].location is None


@pytest.mark.parametrize(
    "item",
    [
        {"kcmc": "课", "xqj": 1, "zcd": "1周"},
        {"kch": "M1", "xqj": 1, "zcd": "1周"},
        {"kch": "M1", "kcmc": "课", "zcd": "1周"},
        {"kch": "M1", "kcmc": "课", "xqj": 1},
        {"kch": "M1", "kcmc": "课", "xqj": 1, "zcd": "第一周"},
        {"kch": "M1", "kcmc": "课", "xqj": 8, "zcd": "1周"},
    ],
)
def test_parse_class_timetable_rejects_invalid_lessons(item: dict[str, object]) -> None:
    with pytest.raises(ParseError):
        parse_class_timetable({"kbList": [item]})


def test_parse_class_timetable_rejects_invalid_payload_shape() -> None:
    with pytest.raises(ParseError, match="JSON object"):
        parse_class_timetable([])
    with pytest.raises(ParseError, match="kbList"):
        parse_class_timetable({"rows": []})
    with pytest.raises(ParseError, match="must be a list"):
        parse_class_timetable({"kbList": {}})


def test_query_class_timetable_raises_on_911() -> None:
    client = _RecordingClient(_FakeResponse(status_code=911))

    with pytest.raises(QueryError, match="911"):
        query_class_timetable(_config(), client, _entry())


def test_query_class_timetable_raises_on_expired_session() -> None:
    client = _RecordingClient(_FakeResponse(status_code=901))

    with pytest.raises(SessionExpiredError, match="901"):
        query_class_timetable(_config(), client, _entry())


def test_query_class_timetable_raises_on_invalid_json() -> None:
    class BadResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json() -> object:
            raise ValueError("bad json")

    client = SimpleNamespace(post=lambda *args, **kwargs: BadResponse())

    with pytest.raises(QueryError, match="not valid JSON"):
        query_class_timetable(_config(), client, _entry())


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (SessionExpiredError("request failed with HTTP 901"), True),
        (QueryError("response is not valid JSON"), False),
    ],
)
def test_is_class_schedule_session_query_failure(
    exc: QueryError, expected: bool
) -> None:
    assert is_class_schedule_session_query_failure(exc) is expected
