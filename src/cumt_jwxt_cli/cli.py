"""Command line interface for cumt-jwxt-cli."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from cumt_jwxt_cli.captcha.openai_compatible import recognize_captcha
from cumt_jwxt_cli.client.auth import login
from cumt_jwxt_cli.client.http import JWXTClient
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
from cumt_jwxt_cli.grades.report import build_text_summary
from cumt_jwxt_cli.grades.service import is_session_query_failure, run_grade_query
from cumt_jwxt_cli.logging_config import configure_logging
from cumt_jwxt_cli.models import AppConfig, RuntimeState
from cumt_jwxt_cli.state import load_runtime_state


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
        previous_state = load_runtime_state(config)
        with JWXTClient(
            timeout_seconds=config.http.timeout_seconds,
            retry_attempts=config.http.retry_attempts,
            retry_backoff_seconds=config.http.retry_backoff_seconds,
            cookies=previous_state.session_cookies,
            trust_env=not args.no_proxy,
        ) as client:
            client.check_reachable()
            result = _run_grade_query_with_session_reuse(
                config=config,
                client=client,
                previous_state=previous_state,
                force_email=args.force_email,
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

    print(
        build_text_summary(
            grades=result.grades,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=result.state.last_successful_query_at or "",
        )
    )
    return int(ExitCode.OK)


def _run_grade_query_with_session_reuse(
    *,
    config: AppConfig,
    client: object,
    previous_state: RuntimeState,
    force_email: bool,
) -> object:
    if not previous_state.session_cookies:
        login(
            config,
            client,
            recognize_captcha=lambda image, app_config: recognize_captcha(
                image,
                app_config.captcha.openai_compatible,
            ),
        )
        return run_grade_query(
            config,
            client,
            previous_state=previous_state,
            session_cookies=client.cookies(),
            session_updated_at=_now_iso(),
            force_email=force_email,
        )

    try:
        return run_grade_query(
            config,
            client,
            previous_state=previous_state,
            session_cookies=client.cookies(),
            force_email=force_email,
        )
    except QueryError as exc:
        if previous_state.session_cookies and is_session_query_failure(exc):
            login(
                config,
                client,
                recognize_captcha=lambda image, app_config: recognize_captcha(
                    image,
                    app_config.captcha.openai_compatible,
                ),
            )
            return run_grade_query(
                config,
                client,
                previous_state=previous_state,
                session_cookies=client.cookies(),
                session_updated_at=_now_iso(),
                force_email=force_email,
            )
        raise


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "parser"):
        args.parser = parser
    return args.handler(args)
