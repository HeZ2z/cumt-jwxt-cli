"""Command line interface for cumt-jwxt-cli."""

import argparse
import sys
from collections.abc import Sequence

from cumt_jwxt_cli.config import load_app_config
from cumt_jwxt_cli.errors import ConfigError, ExitCode

_NOT_IMPLEMENTED_MESSAGE = "grades query is not implemented yet."


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="cumt-jwxt",
        description="CUMT JWXT command line tools.",
    )
    parser.set_defaults(handler=_print_help, parser=parser)

    subparsers = parser.add_subparsers(dest="command")

    grades_parser = subparsers.add_parser("grades", help="Manage grade queries.")
    grades_parser.set_defaults(handler=_print_help, parser=grades_parser)
    grades_subparsers = grades_parser.add_subparsers(dest="grades_command")

    query_parser = grades_subparsers.add_parser(
        "query",
        help="Query grades from CUMT JWXT.",
        description=(
            "Query grades from CUMT JWXT. Business logic is not implemented yet."
        ),
    )
    query_parser.add_argument(
        "--config",
        help=(
            "Path to the local configuration file. Defaults to config.local.json "
            "or config.json in the current or project directory."
        ),
    )
    query_parser.add_argument("--year", help="Academic year, for example 2024.")
    query_parser.add_argument("--semester", help="Semester code, for example 12.")
    query_parser.add_argument(
        "--force-email",
        action="store_true",
        help="Send notification even if no grade changes are detected.",
    )
    query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fail fast instead of prompting for missing configuration.",
    )
    query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save grade JSON output when query logic is implemented.",
    )
    query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save an HTML report when query logic is implemented.",
    )
    query_parser.add_argument(
        "--output-dir",
        help="Directory for optional JSON or report output.",
    )
    query_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output.",
    )
    query_parser.set_defaults(handler=_handle_grades_query, parser=query_parser)

    return parser


def _print_help(args: argparse.Namespace) -> int:
    args.parser.print_help()
    return int(ExitCode.OK)


def _handle_grades_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)

    print(_NOT_IMPLEMENTED_MESSAGE, file=sys.stderr)
    if args.verbose:
        print(
            (
                "Loaded configuration from "
                f"{config.config_path} for {config.query.year}-{config.query.semester}."
            ),
            file=sys.stderr,
        )
    return int(ExitCode.UNKNOWN)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "parser"):
        args.parser = parser
    return args.handler(args)
