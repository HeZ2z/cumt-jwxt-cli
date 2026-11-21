"""Pure free classroom text report generation."""

from __future__ import annotations

from collections.abc import Sequence

from cumt_jwxt_cli.models import FreeClassroom

_CAMPUS_LABELS = {
    "all": "全部校区",
    "nanhu": "南湖校区",
    "wenchang": "文昌校区",
}


def build_classrooms_text_summary(
    *,
    classrooms: Sequence[FreeClassroom],
    total: int,
    date: str,
    start: str | None = None,
    end: str | None = None,
    campus: str = "all",
) -> str:
    """Build a plain-text free classroom summary."""

    time_label = f" {start}-{end}" if start and end else ""
    campus_label = _CAMPUS_LABELS.get(campus, campus)
    lines = [f"CUMT 空闲教室 {date}{time_label}（{campus_label}）"]

    if total == 0:
        lines.append("未找到符合条件的空闲教室。")
        return "\n".join(lines)

    if total > len(classrooms):
        lines.append(f"共 {total} 间，显示前 {len(classrooms)} 间")
    else:
        lines.append(f"共 {total} 间")

    lines.extend(f"- {_format_room(room)}" for room in classrooms)
    return "\n".join(lines)


def _format_room(room: FreeClassroom) -> str:
    name = room.room_name or room.room_code or "--"
    building = room.building or "--"
    location = f"{building} {room.floor}层" if room.floor else f"{building} --"
    seats = f"{room.seats}座" if room.seats else "--"
    category = room.category or "--"
    if room.lendable is True:
        lendable = "可借用"
    elif room.lendable is False:
        lendable = "不可借用"
    else:
        lendable = "--"
    return f"{name} | {location} | {seats} | {category} | {lendable}"
