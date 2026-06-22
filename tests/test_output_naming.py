"""Shared optional output naming tests."""

from cumt_jwxt_cli.output_naming import short_year_semester


def test_short_year_semester_uses_spring_suffix() -> None:
    assert short_year_semester("2026", "12") == "26sp"


def test_short_year_semester_uses_fall_suffix() -> None:
    assert short_year_semester("2026", "3") == "26fa"


def test_short_year_semester_preserves_unknown_semester_code() -> None:
    assert short_year_semester("2026", "1") == "261"
