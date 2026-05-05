"""CLI parser tests."""

from cumt_jwxt_cli.cli import build_parser, main
from cumt_jwxt_cli.errors import ExitCode


def test_build_parser_parses_grades_query() -> None:
    parser = build_parser()

    args = parser.parse_args(["grades", "query"])

    assert args.command == "grades"
    assert args.grades_command == "query"


def test_grades_query_parses_key_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "grades",
            "query",
            "--config",
            "config.test.json",
            "--year",
            "2025",
            "--semester",
            "3",
            "--force-email",
            "--no-interactive",
            "--save-json",
            "--save-report",
            "--output-dir",
            "./out",
            "--verbose",
        ]
    )

    assert args.config == "config.test.json"
    assert args.year == "2025"
    assert args.semester == "3"
    assert args.force_email is True
    assert args.no_interactive is True
    assert args.save_json is True
    assert args.save_report is True
    assert args.output_dir == "./out"
    assert args.verbose is True


def test_main_shows_help_for_grades_command(capsys) -> None:
    exit_code = main(["grades"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.OK)
    assert "usage: cumt-jwxt grades" in captured.out
    assert captured.err == ""


def test_main_returns_non_zero_for_unimplemented_grades_query(capsys) -> None:
    exit_code = main(["grades", "query", "--verbose"])

    captured = capsys.readouterr()

    assert exit_code == int(ExitCode.UNKNOWN)
    assert captured.out == ""
    assert "grades query is not implemented yet." in captured.err
    assert "Parsed grades query arguments successfully." in captured.err
