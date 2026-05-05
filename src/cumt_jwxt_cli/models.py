"""Core data model placeholders."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseGrade:
    """Minimal course grade placeholder."""

    course_code: str
    course_name: str
    score: str
