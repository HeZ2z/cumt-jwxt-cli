"""Helpers for stable optional output artifact naming."""

from __future__ import annotations

_SEMESTER_SUFFIX: dict[str, str] = {
    "3": "fa",
    "12": "sp",
}


def short_year_semester(year: str, semester: str) -> str:
    """Return the shared artifact suffix, for example 26sp or 26fa."""

    short_year = year[-2:] if len(year) >= 2 else year
    sem_label = _SEMESTER_SUFFIX.get(semester, semester)
    return f"{short_year}{sem_label}"
