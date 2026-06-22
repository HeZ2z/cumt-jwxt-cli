"""Command line interface for cumt-jwxt-cli."""

import argparse
import sys
from collections.abc import Sequence

from cumt_jwxt_cli.app import (
    query_exams_with_session_reuse,
    query_grades_with_session_reuse,
)
from cumt_jwxt_cli.config import load_app_config
from cumt_jwxt_cli.errors import (
    AuthError,
    CaptchaError,
    ConfigError,
    ExitCode,
    NotifyError,
    ParseError,
    QueryError,
    SnapshotError,
    StateError,
)
from cumt_jwxt_cli.exams.query_state import (
    exam_query_scope_from_config,
    get_exam_query_state,
)
from cumt_jwxt_cli.exams.report import build_exam_text_summary
from cumt_jwxt_cli.grades.query_state import (
    get_grade_query_state,
    grade_query_scope_from_config,
)
from cumt_jwxt_cli.grades.report import build_text_summary
from cumt_jwxt_cli.logging_config import configure_logging


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
        description="Query grades from CUMT JWXT.",
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
        "--no-proxy",
        action="store_true",
        help="Do not use proxy settings from environment variables.",
    )
    query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fail fast instead of prompting for missing configuration.",
    )
    query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save grade JSON output to the configured output directory.",
    )
    query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save an HTML report to the configured output directory.",
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

    exams_parser = subparsers.add_parser("exams", help="Manage exam schedule queries.")
    exams_parser.set_defaults(handler=_print_help, parser=exams_parser)
    exams_subparsers = exams_parser.add_subparsers(dest="exams_command")

    exams_query_parser = exams_subparsers.add_parser(
        "query",
        help="Query exam schedule from CUMT JWXT.",
        description="Query exam schedule from CUMT JWXT.",
    )
    exams_query_parser.add_argument(
        "--config",
        help=(
            "Path to the local configuration file. Defaults to config.local.json "
            "or config.json in the current or project directory."
        ),
    )
    exams_query_parser.add_argument("--year", help="Academic year, for example 2025.")
    exams_query_parser.add_argument("--semester", help="Semester code, for example 12.")
    exams_query_parser.add_argument(
        "--force-email",
        action="store_true",
        help="Send notification even if no exam changes are detected.",
    )
    exams_query_parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Do not use proxy settings from environment variables.",
    )
    exams_query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fail fast instead of prompting for missing configuration.",
    )
    exams_query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save exam JSON output to the configured output directory.",
    )
    exams_query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save an HTML report to the configured output directory.",
    )
    exams_query_parser.add_argument(
        "--save-ics",
        action="store_true",
        help="Save an ICS calendar file to the configured output directory.",
    )
    exams_query_parser.add_argument(
        "--output-dir",
        help="Directory for optional JSON or report output.",
    )
    exams_query_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output.",
    )
    exams_query_parser.set_defaults(
        handler=_handle_exams_query, parser=exams_query_parser
    )

    return parser


def _print_help(args: argparse.Namespace) -> int:
    args.parser.print_help()
    return int(ExitCode.OK)


def _handle_grades_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_grades_with_session_reuse(
            config,
            force_email=args.force_email,
            trust_env=not args.no_proxy,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)
    except (AuthError, CaptchaError) as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.AUTH_ERROR)
    except QueryError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.QUERY_ERROR)
    except ParseError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.PARSE_ERROR)
    except NotifyError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.NOTIFY_ERROR)
    except (SnapshotError, StateError) as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.UNKNOWN)

    scope = grade_query_scope_from_config(config.query.year, config.query.semester)
    scope_state = get_grade_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_text_summary(
            grades=result.grades,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at,
        )
    )
    return int(ExitCode.OK)


def _handle_exams_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_exams_with_session_reuse(
            config,
            force_email=args.force_email,
            trust_env=not args.no_proxy,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)
    except (AuthError, CaptchaError) as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.AUTH_ERROR)
    except QueryError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.QUERY_ERROR)
    except ParseError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.PARSE_ERROR)
    except NotifyError as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.NOTIFY_ERROR)
    except (SnapshotError, StateError) as exc:
        print(str(exc), file=sys.stderr)
        return int(ExitCode.UNKNOWN)

    scope = exam_query_scope_from_config(config.query.year, config.query.semester)
    scope_state = get_exam_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_exam_text_summary(
            exams=result.exams,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at or "",
        )
    )
    return int(ExitCode.OK)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "parser"):
        args.parser = parser
    return args.handler(args)
