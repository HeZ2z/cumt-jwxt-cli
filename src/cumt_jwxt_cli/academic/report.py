"""Pure academic status text report generation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from cumt_jwxt_cli.models import (
    AcademicSummaryResult,
    CoursePropertyStat,
    PlanRequirementNode,
)

_MISSING = "--"
_MAX_DEPTH = 4


def build_academic_text_summary(result: AcademicSummaryResult) -> str:
    """Build a concise terminal summary of cumulative academic status."""

    overview = result.overview
    lines = [f"CUMT 学业情况（统计时间：{overview.snapshot_at or _MISSING}）"]
    lines.append(
        f"GPA：全部 {_format_gpa(overview.gpa_all)} | "
        f"学位课 {_format_gpa(overview.gpa_degree)}"
    )
    lines.append(
        "计划课程："
        f"总 {_count(overview.plan_total)}，"
        f"通过 {_count(overview.plan_passed)}，"
        f"未通过 {_count(overview.plan_failed)}，"
        f"未修 {_count(overview.plan_unlearned)}，"
        f"在读 {_count(overview.plan_in_progress)}"
    )
    lines.append(
        "计划外："
        f"通过 {_count(overview.out_of_plan_passed)}，"
        f"未通过 {_count(overview.out_of_plan_failed)}"
    )

    lines.append("")
    lines.extend(_format_plan(result.plan_nodes))
    lines.append("按课程性质")
    if result.property_stats:
        lines.extend(_format_property(stat) for stat in result.property_stats)
    else:
        lines.append("  （无数据）")
    return "\n".join(lines)


def _format_plan(nodes: tuple[PlanRequirementNode, ...]) -> list[str]:
    total_required, total_earned = _root_credit_totals(nodes)
    lines = [
        "培养方案"
        f"（要求 {_format_credits(total_required)} / "
        f"已获 {_format_credits(total_earned)}）"
    ]
    if not nodes:
        lines.append("  （无数据）")
        return lines

    by_id = {node.node_id: node for node in nodes}
    for node in nodes:
        depth = _node_depth(node, by_id)
        indent = "  " * min(depth, _MAX_DEPTH)
        name = node.name or node.node_id or _MISSING
        credits = (
            f"{_format_credits(node.required_credits)}/"
            f"{_format_credits(node.earned_credits)}"
        )
        status = _plan_status(node)
        lines.append(f"{indent}- {name} {credits} {status}")
    return lines


def _format_property(stat: CoursePropertyStat) -> str:
    name = stat.property_name or stat.property_code or _MISSING
    return (
        f"- {name} GPA {_format_gpa(stat.gpa)} | "
        f"加权 {_format_gpa(stat.weighted_average)} | "
        f"{_format_credits(stat.earned_credits)} 学分"
    )


def _root_credit_totals(
    nodes: tuple[PlanRequirementNode, ...],
) -> tuple[Decimal | None, Decimal | None]:
    ids = {node.node_id for node in nodes}
    required_values: list[Decimal] = []
    earned_values: list[Decimal] = []

    for node in nodes:
        is_root = node.parent_id is None or node.parent_id not in ids
        if not is_root or node.parent_id == node.node_id:
            continue
        required = _to_decimal(node.required_credits)
        earned = _to_decimal(node.earned_credits)
        if required is not None:
            required_values.append(required)
        if earned is not None:
            earned_values.append(earned)

    required_total = sum(required_values, Decimal(0)) if required_values else None
    earned_total = sum(earned_values, Decimal(0)) if earned_values else None
    return required_total, earned_total


def _node_depth(
    node: PlanRequirementNode,
    by_id: dict[str, PlanRequirementNode],
) -> int:
    depth = 0
    current = node
    seen = {node.node_id}
    while current.parent_id is not None:
        parent = by_id.get(current.parent_id)
        if parent is None or parent.node_id in seen:
            break
        seen.add(parent.node_id)
        depth += 1
        current = parent
    return depth


def _plan_status(node: PlanRequirementNode) -> str:
    required = _to_decimal(node.required_credits)
    earned = _to_decimal(node.earned_credits)
    if required is None or earned is None:
        if node.is_passed is True:
            return "已满"
        if node.is_passed is False:
            return "未满"
        return _MISSING
    if earned >= required:
        return "已满"
    remaining = required - earned
    return f"未满（差 {_format_credits(remaining)}）"


def _format_gpa(value: str | None) -> str:
    number = _to_decimal(value)
    if number is None:
        return _MISSING
    return f"{number:.2f}"


def _format_credits(value: Decimal | str | None) -> str:
    number = value if isinstance(value, Decimal) else _to_decimal(value)
    if number is None:
        return _MISSING
    return f"{number:.1f}"


def _count(value: str | None) -> str:
    return value if value else _MISSING


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.strip()
    if text in {"", _MISSING, "-", "None", "null"}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None
