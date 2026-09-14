"""ICS calendar file generation from personal schedule data."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta, timezone

from icalendar import Alarm, Calendar, Event, Timezone, TimezoneStandard
from icalendar.prop import vRecur

from cumt_jwxt_cli.models import PeriodTime, ScheduleLesson, ScheduleSlot
from cumt_jwxt_cli.output_naming import short_year_semester

logger = logging.getLogger(__name__)

_PERIOD_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
_CLOCK_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")

# China has no daylight saving time, so a fixed offset avoids depending on the
# system tzdata being present (not guaranteed on Windows).
_CST = timezone(timedelta(hours=8))


class _OrderedRecur(vRecur):
    """Weekly RRULE serialized as FREQ, INTERVAL, UNTIL."""

    canonical_order = ("FREQ", "INTERVAL", "UNTIL")


def build_ics_filename(year: str, semester: str) -> str:
    return f"schedule_{short_year_semester(year, semester)}.ics"


def split_week_runs(weeks: tuple[int, ...]) -> list[tuple[tuple[int, ...], int]]:
    """Split sorted weeks into maximal runs of constant weekly interval.

    Consecutive weeks separated by one are grouped with INTERVAL=1, while a
    pure odd/even sequence separated by two is grouped with INTERVAL=2.
    """

    ordered = tuple(sorted(set(weeks)))
    runs: list[tuple[tuple[int, ...], int]] = []
    index = 0
    while index < len(ordered):
        if index == len(ordered) - 1:
            runs.append(((ordered[index],), 1))
            break
        interval = ordered[index + 1] - ordered[index]
        if interval not in (1, 2):
            runs.append(((ordered[index],), 1))
            index += 1
            continue
        end = index + 1
        while end + 1 < len(ordered) and ordered[end + 1] - ordered[end] == interval:
            end += 1
        runs.append((ordered[index : end + 1], interval))
        index = end + 1
    return runs


def build_ics_content(
    lessons: Sequence[ScheduleLesson],
    period_times: Sequence[PeriodTime],
    week_dates: Mapping[int, date],
    year: str,
    semester: str,
) -> str:
    """Build an ICS calendar from parsed lessons and JWXT lookup tables."""

    period_lookup = {period.period: period for period in period_times}

    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", "-//cumt-jwxt-cli//Schedule//EN")
    cal.add("X-WR-CALNAME", f"CUMT 个人课表 {year}-{semester}")
    cal.add("X-WR-CALDESC", f"CUMT schedule for {year} semester {semester}")

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

    dtstamp = datetime.now(UTC)
    for lesson in lessons:
        for slot in lesson.slots:
            _add_slot_events(cal, lesson, slot, period_lookup, week_dates, dtstamp)

    return cal.to_ical().decode("utf-8")


def _add_slot_events(
    cal: Calendar,
    lesson: ScheduleLesson,
    slot: ScheduleSlot,
    period_lookup: Mapping[str, PeriodTime],
    week_dates: Mapping[int, date],
    dtstamp: datetime,
) -> None:
    if not slot.weeks:
        logger.warning(
            "Skipping schedule slot %s %s: no weeks",
            lesson.course_code,
            lesson.course_name,
        )
        return

    bounds = _period_bounds(slot.periods)
    if bounds is None:
        logger.warning(
            "Skipping schedule slot %s %s: unparseable periods '%s'",
            lesson.course_code,
            lesson.course_name,
            slot.periods,
        )
        return
    start_period, end_period = bounds
    start_time = _clock_time(period_lookup.get(str(start_period)), use_end=False)
    end_time = _clock_time(period_lookup.get(str(end_period)), use_end=True)
    if start_time is None or end_time is None:
        logger.warning(
            "Skipping schedule slot %s %s: missing period times for '%s'",
            lesson.course_code,
            lesson.course_name,
            slot.periods,
        )
        return

    for run_weeks, interval in split_week_runs(slot.weeks):
        first_monday = week_dates.get(run_weeks[0])
        last_monday = week_dates.get(run_weeks[-1])
        if first_monday is None or last_monday is None:
            logger.warning(
                "Skipping schedule slot %s %s: missing week dates for %s",
                lesson.course_code,
                lesson.course_name,
                run_weeks,
            )
            continue

        start_date = first_monday + timedelta(days=slot.weekday - 1)
        last_date = last_monday + timedelta(days=slot.weekday - 1)

        event = Event()
        event.add("DTSTAMP", dtstamp)
        event.add("UID", _build_uid(lesson, slot, run_weeks[0], interval))
        event.add("SUMMARY", lesson.course_name)

        event.add("DTSTART", datetime.combine(start_date, start_time))
        event["DTSTART"].params["TZID"] = "Asia/Shanghai"
        event.add("DTEND", datetime.combine(start_date, end_time))
        event["DTEND"].params["TZID"] = "Asia/Shanghai"

        rrule = _OrderedRecur()
        rrule["FREQ"] = ["WEEKLY"]
        rrule["INTERVAL"] = [interval]
        rrule["UNTIL"] = [_until_datetime(last_date, interval)]
        event.add("RRULE", rrule)

        location = _join_non_empty(slot.location, lesson.teacher)
        if location:
            event.add("LOCATION", location)

        event.add(
            "DESCRIPTION",
            f"第{start_period} - {end_period}节\n{slot.location or ''}\n"
            f"{lesson.teacher or ''}",
        )

        alarm = Alarm()
        alarm.add("ACTION", "DISPLAY")
        alarm.add("TRIGGER", timedelta(minutes=-20))
        alarm["TRIGGER"].params["RELATED"] = "START"
        alarm.add("DESCRIPTION", f"{lesson.course_name}@{slot.location or ''}\n")
        event.add_component(alarm)

        cal.add_component(event)


def _build_uid(
    lesson: ScheduleLesson,
    slot: ScheduleSlot,
    first_week: int,
    interval: int,
) -> str:
    raw = (
        f"{lesson.course_code}|{lesson.teaching_class or ''}|{slot.weekday}|"
        f"{slot.periods}|{slot.location or ''}|{first_week}|{interval}"
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"cumt-jwxt-schedule-{digest}"


def _until_datetime(last_date: date, interval: int) -> datetime:
    local = datetime.combine(last_date, time.min, tzinfo=_CST) + timedelta(
        days=7 * interval
    )
    return local.astimezone(UTC)


def _period_bounds(periods: str) -> tuple[int, int] | None:
    match = _PERIOD_PATTERN.match(periods)
    if match is None:
        return None
    start = int(match[1])
    end = int(match[2]) if match[2] is not None else start
    return (start, end)


def _clock_time(period: PeriodTime | None, *, use_end: bool) -> time | None:
    if period is None:
        return None
    raw = period.end if use_end else period.start
    match = _CLOCK_PATTERN.match(raw.strip())
    if match is None:
        return None
    return time(hour=int(match[1]), minute=int(match[2]))


def _join_non_empty(*values: str | None) -> str:
    return " ".join(value for value in values if value)
