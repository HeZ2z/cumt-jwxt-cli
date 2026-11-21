"""Teaching plan service orchestration tests."""

from types import SimpleNamespace

import pytest

import cumt_jwxt_cli.plan.service as service_module
from cumt_jwxt_cli.errors import ConfigError
from cumt_jwxt_cli.models import TeachingPlanCourse, TeachingPlanHeader
from cumt_jwxt_cli.plan.query_fetch import PlanFilters
from cumt_jwxt_cli.plan.service import run_plan_query


def _config() -> SimpleNamespace:
    return SimpleNamespace(query=SimpleNamespace(year="2026", semester="3"))


def _header(**overrides: object) -> TeachingPlanHeader:
    values: dict[str, object] = {
        "plan_id": "PLAN-1",
        "grade": "2023",
        "major_code": "0810",
        "major_name": "计算机科学与技术",
        "college_id": "08",
        "campus": "南湖校区",
        "program_length": "4",
        "course_count": "112",
        "total_credits": "171.0",
    }
    values.update(overrides)
    return TeachingPlanHeader(**values)  # type: ignore[arg-type]


def _course(**overrides: object) -> TeachingPlanCourse:
    values: dict[str, object] = {
        "course_code": "M1",
        "course_name": "高等数学",
        "course_name_en": "Advanced Mathematics",
        "credits": "5.0",
        "total_hours": "80",
        "study_year": "2023",
        "study_term": "3",
        "allowed_terms": None,
        "category_name": "通识必修",
        "class_category": "公共基础课",
        "assessment_method": "考试",
        "exam_method": "闭卷",
        "department": "数学学院",
        "week_range": "1-16",
        "study_type": "zx",
        "status": "0",
    }
    values.update(overrides)
    return TeachingPlanCourse(**values)  # type: ignore[arg-type]


def _patch_queries(monkeypatch, *, headers, courses):
    header_calls: list[PlanFilters] = []
    course_calls: list[tuple[PlanFilters, str]] = []

    def fake_headers(config, client, filters):
        header_calls.append(filters)
        return tuple(headers)

    def fake_courses(config, client, filters, plan_id):
        course_calls.append((filters, plan_id))
        return tuple(courses)

    monkeypatch.setattr(service_module, "query_plan_headers", fake_headers)
    monkeypatch.setattr(service_module, "query_plan_courses", fake_courses)
    return header_calls, course_calls


def test_plan_id_is_used_directly_without_header_lookup(monkeypatch) -> None:
    header_calls, course_calls = _patch_queries(
        monkeypatch, headers=[], courses=[_course()]
    )

    result = run_plan_query(_config(), object(), PlanFilters(plan_id="PLAN-1"))

    assert header_calls == []
    assert len(course_calls) == 1
    assert course_calls[0][1] == "PLAN-1"
    assert result.header is not None
    assert result.header.plan_id == "PLAN-1"
    assert result.header.course_count == "1"
    assert len(result.courses) == 1


def test_single_matching_plan_is_selected_automatically(monkeypatch) -> None:
    header_calls, course_calls = _patch_queries(
        monkeypatch, headers=[_header()], courses=[_course()]
    )

    result = run_plan_query(
        _config(),
        object(),
        PlanFilters(grade="2023", college="08", major="0810"),
    )

    assert len(header_calls) == 1
    assert len(course_calls) == 1
    assert course_calls[0][1] == "PLAN-1"
    assert result.header is not None
    assert result.header.major_name == "计算机科学与技术"


def test_multiple_matching_plans_require_plan_id(monkeypatch) -> None:
    _patch_queries(
        monkeypatch,
        headers=[_header(plan_id="A"), _header(plan_id="B")],
        courses=[],
    )

    with pytest.raises(ConfigError, match="--list"):
        run_plan_query(_config(), object(), PlanFilters(grade="2023"))


def test_missing_lookup_filter_is_rejected(monkeypatch) -> None:
    header_calls, course_calls = _patch_queries(monkeypatch, headers=[], courses=[])

    with pytest.raises(ConfigError, match="--plan-id"):
        run_plan_query(_config(), object(), PlanFilters())

    assert header_calls == []
    assert course_calls == []


def test_list_only_returns_plans_without_course_query(monkeypatch) -> None:
    header_calls, course_calls = _patch_queries(
        monkeypatch, headers=[_header()], courses=[]
    )

    result = run_plan_query(
        _config(), object(), PlanFilters(grade="2023", list_only=True)
    )

    assert len(header_calls) == 1
    assert course_calls == []
    assert result.list_only is True
    assert result.total == 1
    assert result.plans[0].plan_id == "PLAN-1"


def test_course_keyword_matches_code_or_name(monkeypatch) -> None:
    _patch_queries(
        monkeypatch,
        headers=[_header()],
        courses=[
            _course(course_code="M1", course_name="高等数学"),
            _course(course_code="CS2", course_name="数据结构"),
        ],
    )

    result = run_plan_query(
        _config(),
        object(),
        PlanFilters(grade="2023", course="数学"),
    )

    assert [course.course_code for course in result.courses] == ["M1"]


def test_course_filters_by_year_term_and_type(monkeypatch) -> None:
    _patch_queries(
        monkeypatch,
        headers=[_header()],
        courses=[
            _course(
                course_code="A", study_year="2023", study_term="3", study_type="zx"
            ),
            _course(
                course_code="B", study_year="2024", study_term="12", study_type="fx"
            ),
            _course(
                course_code="C", study_year="2023", study_term="12", study_type="zx"
            ),
        ],
    )

    result = run_plan_query(
        _config(),
        object(),
        PlanFilters(grade="2023", study_year="2023", study_term="3", study_type="zx"),
    )

    assert [course.course_code for course in result.courses] == ["A"]


def test_course_filters_match_real_year_range_and_display_terms(monkeypatch) -> None:
    _patch_queries(
        monkeypatch,
        headers=[_header()],
        courses=[
            _course(
                course_code="A",
                study_year="2023-2024",
                study_term="1",
                allowed_terms="2023-2024/1",
            ),
            _course(
                course_code="B",
                study_year="2024-2025",
                study_term="2",
                allowed_terms="2024-2025/2",
            ),
        ],
    )

    result = run_plan_query(
        _config(),
        object(),
        PlanFilters(grade="2023", study_year="2023", study_term="3"),
    )

    assert [course.course_code for course in result.courses] == ["A"]


def test_courses_are_sorted_by_numeric_year_and_term(monkeypatch) -> None:
    _patch_queries(
        monkeypatch,
        headers=[_header()],
        courses=[
            _course(course_code="C", study_year="2024", study_term="3"),
            _course(course_code="B", study_year="2023", study_term="12"),
            _course(course_code="A", study_year="2023", study_term="3"),
        ],
    )

    result = run_plan_query(_config(), object(), PlanFilters(grade="2023"))

    assert [course.course_code for course in result.courses] == ["A", "B", "C"]
