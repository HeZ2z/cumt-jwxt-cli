"""Teaching plan text report tests."""

from cumt_jwxt_cli.models import (
    TeachingPlanCourse,
    TeachingPlanHeader,
    TeachingPlanResult,
)
from cumt_jwxt_cli.plan.report import (
    build_plan_list_text,
    build_plan_text_summary,
)


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
        "course_name": "计算机新技术（英语）",
        "course_name_en": "New Computer Technology",
        "credits": "2.0",
        "total_hours": "32",
        "study_year": "2023",
        "study_term": "3",
        "allowed_terms": None,
        "category_name": "通识必修",
        "class_category": "公共基础课",
        "assessment_method": "考试",
        "exam_method": "考试",
        "department": "计算机学院",
        "week_range": "1-16",
        "study_type": "zx",
        "status": "0",
    }
    values.update(overrides)
    return TeachingPlanCourse(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> TeachingPlanResult:
    values: dict[str, object] = {
        "header": _header(),
        "courses": (_course(),),
        "plans": (),
        "total": 1,
        "list_only": False,
    }
    values.update(overrides)
    return TeachingPlanResult(**values)  # type: ignore[arg-type]


def test_summary_renders_header_and_course_line() -> None:
    text = build_plan_text_summary(_result())

    assert "CUMT 教学执行计划" in text
    assert "计划：计算机科学与技术（2023） | 112 门 | 总学分 171.0" in text
    assert "2023-2024 第1学期" in text
    assert "- 计算机新技术（英语） | 2.0 学分 | 32 学时 | 通识必修 | 考试" in text


def test_summary_groups_courses_by_term() -> None:
    result = _result(
        courses=(
            _course(course_name="A", study_term="3"),
            _course(course_name="B", study_term="12"),
            _course(course_name="C", study_term="12"),
        )
    )

    text = build_plan_text_summary(result)

    assert "2023-2024 第1学期" in text
    assert "2023-2024 第2学期" in text
    assert text.index("第1学期") < text.index("第2学期")


def test_summary_uses_placeholders_for_missing_fields() -> None:
    result = _result(
        header=_header(
            grade=None,
            major_name=None,
            course_count=None,
            total_credits=None,
        ),
        courses=(
            _course(
                course_name=None,
                course_code="M9",
                credits=None,
                total_hours=None,
                category_name=None,
                class_category=None,
                assessment_method=None,
                exam_method=None,
            ),
        ),
    )

    text = build_plan_text_summary(result)

    assert "计划：PLAN-1 | 1 门" in text
    assert "总学分" not in text
    assert "- M9 | -- 学分 | -- 学时 | -- | --" in text


def test_summary_uses_year_range_when_present() -> None:
    result = _result(
        courses=(
            _course(
                study_year="2023-2024",
                study_term="1",
                allowed_terms="2023-2024/1",
            ),
        )
    )

    text = build_plan_text_summary(result)

    assert "2023-2024 第1学期" in text
    assert "2023-2024-2023-2024" not in text


def test_summary_reports_empty_course_list() -> None:
    text = build_plan_text_summary(_result(courses=(), total=0))

    assert "该计划没有匹配的课程。" in text


def test_summary_shows_filter_conditions() -> None:
    result = _result(
        courses=(_course(),),
        study_year="2023",
        study_term="3",
        course_query="数学",
        study_type="zx",
    )

    text = build_plan_text_summary(result)

    assert "条件：学期 2023-2024 第1学期 | 课程 数学 | 类型 主修" in text


def test_list_renders_plan_options_and_empty_state() -> None:
    text = build_plan_list_text(plans=[_header()], total=1)

    assert "CUMT 教学执行计划列表" in text
    assert "匹配 1 个教学执行计划" in text
    assert "- 2023 计算机科学与技术 | PLAN-1 | 112 门 | 171.0 学分" in text

    empty = build_plan_list_text(plans=[], total=0)
    assert "未找到匹配的教学执行计划。" in empty
