"""Teaching execution plan query business orchestration."""

from __future__ import annotations

from cumt_jwxt_cli.errors import ConfigError
from cumt_jwxt_cli.models import (
    AppConfig,
    TeachingPlanCourse,
    TeachingPlanHeader,
    TeachingPlanResult,
)
from cumt_jwxt_cli.plan.query_fetch import (
    PlanFilters,
    query_plan_courses,
    query_plan_headers,
)


def run_plan_query(
    config: AppConfig,
    client: object,
    filters: PlanFilters,
) -> TeachingPlanResult:
    """Locate a teaching plan and return its courses.

    Teaching plans are tied to a major/grade, not to a term, so ``config.query``
    is intentionally ignored.
    """

    _require_lookup_filter(filters)

    if filters.plan_id:
        return _run_for_plan_id(config, client, filters)

    headers = query_plan_headers(config, client, filters)
    if filters.list_only:
        return TeachingPlanResult(
            header=None,
            courses=(),
            plans=headers,
            total=len(headers),
            list_only=True,
            course_query=filters.course,
            study_year=filters.study_year,
            study_term=filters.study_term,
            study_type=filters.study_type,
        )

    header = _select_header(headers)
    courses = query_plan_courses(config, client, filters, plan_id=_require_id(header))
    return _build_result(header, courses, filters)


def _run_for_plan_id(
    config: AppConfig,
    client: object,
    filters: PlanFilters,
) -> TeachingPlanResult:
    plan_id = filters.plan_id or ""
    header: TeachingPlanHeader | None = None
    if filters.has_header_filter:
        headers = query_plan_headers(config, client, filters)
        header = next(
            (item for item in headers if item.plan_id == plan_id),
            None,
        )
        if header is None and not filters.list_only:
            raise ConfigError(f"未找到计划 ID 为 {plan_id} 的教学执行计划。")

    if filters.list_only:
        if header is None and not filters.has_header_filter:
            courses = query_plan_courses(config, client, filters, plan_id=plan_id)
            header = _synthetic_header(plan_id, courses)
        plans = (header,) if header is not None else ()
        return TeachingPlanResult(
            header=None,
            courses=(),
            plans=plans,
            total=len(plans),
            list_only=True,
            course_query=filters.course,
            study_year=filters.study_year,
            study_term=filters.study_term,
            study_type=filters.study_type,
        )

    courses = query_plan_courses(config, client, filters, plan_id=plan_id)
    if header is None:
        header = _synthetic_header(plan_id, courses)
    return _build_result(header, courses, filters)


def _build_result(
    header: TeachingPlanHeader,
    courses: tuple[TeachingPlanCourse, ...],
    filters: PlanFilters,
) -> TeachingPlanResult:
    filtered = _filter_courses(courses, filters)
    return TeachingPlanResult(
        header=header,
        courses=tuple(sorted(filtered, key=_course_sort_key)),
        plans=(),
        total=len(filtered),
        list_only=False,
        course_query=filters.course,
        study_year=filters.study_year,
        study_term=filters.study_term,
        study_type=filters.study_type,
    )


def _require_lookup_filter(filters: PlanFilters) -> None:
    if filters.plan_id or filters.has_header_filter:
        return
    raise ConfigError(
        "请提供 --plan-id，或用 --grade/--college/--major 缩小范围（可配合 --list）。"
    )


def _select_header(
    headers: tuple[TeachingPlanHeader, ...],
) -> TeachingPlanHeader:
    if not headers:
        raise ConfigError("未找到匹配的教学执行计划。")
    if len(headers) > 1:
        raise ConfigError(
            f"匹配到 {len(headers)} 个教学执行计划，"
            "请用 --list 查看并用 --plan-id 指定。"
        )
    return headers[0]


def _require_id(header: TeachingPlanHeader) -> str:
    if not header.plan_id:
        raise ConfigError("教学执行计划缺少计划 ID，无法查询课程。")
    return header.plan_id


def _synthetic_header(
    plan_id: str,
    courses: tuple[TeachingPlanCourse, ...],
) -> TeachingPlanHeader:
    # A plan id alone has no header lookup endpoint; still report the id and the
    # fetched course count instead of showing an empty header.
    return TeachingPlanHeader(
        plan_id=plan_id,
        grade=None,
        major_code=None,
        major_name=None,
        college_id=None,
        campus=None,
        program_length=None,
        course_count=str(len(courses)),
        total_credits=None,
    )


def _filter_courses(
    courses: tuple[TeachingPlanCourse, ...],
    filters: PlanFilters,
) -> tuple[TeachingPlanCourse, ...]:
    result = courses
    if filters.course:
        text = filters.course.strip().casefold()
        if text:
            result = tuple(
                course
                for course in result
                if text in (course.course_code or "").casefold()
                or text in (course.course_name or "").casefold()
            )
    if filters.study_year:
        result = tuple(
            course
            for course in result
            if _matches_study_year(course.study_year, filters.study_year)
        )
    if filters.study_term:
        result = tuple(
            course
            for course in result
            if _matches_study_term(course.study_term, filters.study_term)
        )
    if filters.study_type:
        result = tuple(
            course
            for course in result
            if (course.study_type or "").casefold() == filters.study_type.casefold()
        )
    return result


def _course_sort_key(course: TeachingPlanCourse) -> tuple[int, int, str, str]:
    return (
        _sort_int(course.study_year),
        _sort_int(course.study_term),
        course.course_code or "",
        course.course_name or "",
    )


# The plan course endpoint filters by JWXT's input codes 3/12/16 but returns
# rows labelled with semester indices 1/2/3. Accept either form when filtering
# the already server-filtered rows again.
_DISPLAY_TERMS: dict[str, str] = {"3": "1", "12": "2", "16": "3"}


def _matches_study_year(value: str | None, expected: str) -> bool:
    if value == expected:
        return True
    # Rows store an academic-year range (2023-2024) while the filter takes the
    # start year (2023).
    return value is not None and value.startswith(f"{expected}-")


def _matches_study_term(value: str | None, expected: str) -> bool:
    if value == expected:
        return True
    return value == _DISPLAY_TERMS.get(expected)


def _sort_int(value: str | None) -> int:
    if value is None:
        return 0
    # Academic-year rows look like 2023-2024; sort by the start year.
    text = value.split("-", 1)[0]
    try:
        return int(text)
    except ValueError:
        return 0
