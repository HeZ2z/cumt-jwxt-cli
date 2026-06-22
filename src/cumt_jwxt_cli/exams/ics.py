"""ICS calendar file generation from exam schedule data."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event, Timezone, TimezoneStandard

from cumt_jwxt_cli.models import ExamInfo
from cumt_jwxt_cli.output_naming import short_year_semester

logger = logging.getLogger(__name__)

_EXAM_TIME_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})\((\d{2}):(\d{2})-(\d{2}):(\d{2})\)$"
)

def build_ics_filename(year: str, semester: str) -> str:
    return f"exam_schedule_{short_year_semester(year, semester)}.ics"


def _build_uid(exam: ExamInfo) -> str:
    raw = f"{exam.course_code}|{exam.exam_time or ''}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"cumt-jwxt-exam-{digest}"


def _parse_exam_time(
    exam_time: str,
) -> tuple[int, int, int, int, int, int, int, int] | None:
    """Parse YYYY-MM-DD(HH:MM-HH:MM) into (y,m,d,sh,sm,eh,em)."""
    m = _EXAM_TIME_PATTERN.match(exam_time)
    if not m:
        return None
    return (
        int(m[1]),
        int(m[2]),
        int(m[3]),
        int(m[4]),
        int(m[5]),
        int(m[6]),
        int(m[7]),
    )


def build_ics_content(
    exams: Sequence[ExamInfo],
    year: str,
    semester: str,
) -> str:
    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("X-WR-CALNAME", f"CUMT 考试安排 {year}-{semester}")
    cal.add("X-WR-CALDESC", f"CUMT exam schedule for {year} semester {semester}")

    tz = Timezone()
    tz.add("TZID", "Asia/Shanghai")
    tz.add("LAST-MODIFIED", datetime.now(UTC))
    tz.add("TZURL", "https://www.tzurl.org/zoneinfo-outlook/Asia/Shanghai")
    tz.add("X-LIC-LOCATION", "Asia/Shanghai")
    std = TimezoneStandard()
    std.add("TZNAME", "CST")
    std.add("TZOFFSETFROM", timedelta(hours=8))
    std.add("TZOFFSETTO", timedelta(hours=8))
    std.add("DTSTART", datetime(1970, 1, 1))
    tz.add_component(std)
    cal.add_component(tz)

    now_utc = datetime.now(UTC)
    dtstamp = now_utc

    for exam in exams:
        if not exam.exam_time:
            logger.warning(
                "Skipping exam %s %s: missing exam_time",
                exam.course_code,
                exam.course_name,
            )
            continue

        parsed = _parse_exam_time(exam.exam_time)
        if parsed is None:
            logger.warning(
                "Skipping exam %s %s: unparseable exam_time '%s'",
                exam.course_code,
                exam.course_name,
                exam.exam_time,
            )
            continue

        yr, mo, dy, start_h, start_m, end_h, end_m = parsed

        event = Event()
        event.add("DTSTAMP", dtstamp)
        event.add("UID", _build_uid(exam))

        summary = exam.course_name
        if exam.exam_name:
            summary = f"{summary} {exam.exam_name}"
        event.add("SUMMARY", summary)

        event.add("DTSTART", datetime(yr, mo, dy, start_h, start_m, 0))
        event["DTSTART"].params["TZID"] = "Asia/Shanghai"
        event.add("DTEND", datetime(yr, mo, dy, end_h, end_m, 0))
        event["DTEND"].params["TZID"] = "Asia/Shanghai"

        if exam.location:
            event.add("LOCATION", exam.location)

        desc_parts: list[str] = [exam.course_code]
        if exam.campus:
            desc_parts.append(exam.campus)
        if exam.location:
            desc_parts.append(exam.location)
        if exam.exam_method:
            desc_parts.append(exam.exam_method)
        event.add("DESCRIPTION", "\n".join(desc_parts))

        cal.add_component(event)

    return cal.to_ical().decode("utf-8")
