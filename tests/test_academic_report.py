"""Academic status text report tests."""

from cumt_jwxt_cli.academic.report import build_academic_text_summary
from cumt_jwxt_cli.models import (
    AcademicOverview,
    AcademicSummaryResult,
    CoursePropertyStat,
    PlanRequirementNode,
)


def _overview(**overrides: object) -> AcademicOverview:
    values = {
        "snapshot_at": "2026-11-21 08:30",
        "gpa_all": "3.216",
        "gpa_degree": "3.05",
        "plan_total": "108",
        "plan_passed": "75",
        "plan_failed": "0",
        "plan_unlearned": "29",
        "plan_in_progress": "4",
        "out_of_plan_passed": "9",
        "out_of_plan_failed": "2",
    }
    values.update(overrides)
    return AcademicOverview(**values)


def _node(
    node_id: str,
    name: str | None,
    parent_id: str | None,
    required: str | None,
    earned: str | None,
    passed: bool | None = None,
) -> PlanRequirementNode:
    return PlanRequirementNode(
        node_id=node_id,
        name=name,
        parent_id=parent_id,
        required_credits=required,
        earned_credits=earned,
        is_passed=passed,
    )


def test_build_academic_text_summary_formats_overview_and_gpa() -> None:
    result = AcademicSummaryResult(
        overview=_overview(), plan_nodes=(), property_stats=()
    )

    text = build_academic_text_summary(result)

    assert "CUMT 学业情况（统计时间：2026-11-21 08:30）" in text
    assert "GPA：全部 3.22 | 学位课 3.05" in text
    assert "计划课程：总 108，通过 75，未通过 0，未修 29，在读 4" in text
    assert "计划外：通过 9，未通过 2" in text
    assert "（无数据）" in text


def test_build_academic_text_summary_shows_missing_values() -> None:
    result = AcademicSummaryResult(
        overview=_overview(
            snapshot_at=None,
            gpa_all=None,
            gpa_degree=None,
            plan_total=None,
            plan_passed=None,
            plan_failed=None,
            plan_unlearned=None,
            plan_in_progress=None,
            out_of_plan_passed=None,
            out_of_plan_failed=None,
        ),
        plan_nodes=(),
        property_stats=(),
    )

    text = build_academic_text_summary(result)

    assert "统计时间：--" in text
    assert "GPA：全部 -- | 学位课 --" in text
    assert "计划课程：总 --，通过 --，未通过 --，未修 --，在读 --" in text


def test_build_academic_text_summary_indents_plan_tree() -> None:
    nodes = (
        _node("1", "通识教育课程", None, "171.0", "148.5", False),
        _node("2", "通识教育必修课", "1", "45.0", "45.0", True),
        _node("3", "通识教育选修课", "1", "20.0", "10.0", False),
        _node("5", "子节点", "3", "5.0", "2.0", False),
        _node("4", "状态缺失", None, None, None, True),
    )
    result = AcademicSummaryResult(
        overview=_overview(), plan_nodes=nodes, property_stats=()
    )

    text = build_academic_text_summary(result)

    assert "培养方案（要求 171.0 / 已获 148.5）" in text
    assert "- 通识教育课程 171.0/148.5 未满（差 22.5）" in text
    assert "  - 通识教育必修课 45.0/45.0 已满" in text
    assert "  - 通识教育选修课 20.0/10.0 未满（差 10.0）" in text
    assert "    - 子节点 5.0/2.0 未满（差 3.0）" in text
    assert "- 状态缺失 --/-- 已满" in text


def test_build_academic_text_summary_formats_property_stats() -> None:
    result = AcademicSummaryResult(
        overview=_overview(),
        plan_nodes=(),
        property_stats=(
            CoursePropertyStat(
                property_code="k1",
                property_name="通识教育必修课",
                gpa="2.18",
                weighted_average="71.39",
                earned_credits="37.5",
            ),
            CoursePropertyStat(
                property_code="k2",
                property_name=None,
                gpa=None,
                weighted_average=None,
                earned_credits=None,
            ),
        ),
    )

    text = build_academic_text_summary(result)

    assert "- 通识教育必修课 GPA 2.18 | 加权 71.39 | 37.5 学分" in text
    assert "- k2 GPA -- | 加权 -- | -- 学分" in text


def test_build_academic_text_summary_handles_cycles_and_depth_cap() -> None:
    nodes = (
        _node("a", "甲", "b", "10", "1", False),
        _node("b", "乙", "a", "10", "1", False),
        _node("d1", "层1", None, "1", "0", False),
        _node("d2", "层2", "d1", "1", "0", False),
        _node("d3", "层3", "d2", "1", "0", False),
        _node("d4", "层4", "d3", "1", "0", False),
        _node("d5", "层5", "d4", "1", "0", False),
        _node("d6", "层6", "d5", "1", "0", False),
    )
    result = AcademicSummaryResult(
        overview=_overview(), plan_nodes=nodes, property_stats=()
    )

    text = build_academic_text_summary(result)

    assert "- 甲" in text
    assert "- 乙" in text
    assert "        - 层6 1.0/0.0 未满（差 1.0）" in text
