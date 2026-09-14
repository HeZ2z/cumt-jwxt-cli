"""Command line interface for cumt-jwxt-cli."""

import argparse
import sys
from collections.abc import Sequence

from cumt_jwxt_cli.app import (
    query_exams_with_session_reuse,
    query_grades_with_session_reuse,
    query_schedule_with_session_reuse,
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
from cumt_jwxt_cli.schedule.query_state import (
    get_schedule_query_state,
    schedule_query_scope_from_config,
)
from cumt_jwxt_cli.schedule.report import build_schedule_text_summary

_USAGE_PREFIX = "用法: "
_HELP_FLAG_HELP = "显示帮助信息并退出。"


class _ChineseHelpFormatter(argparse.HelpFormatter):
    """Render argparse's auto-generated usage label in Chinese."""

    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(
            usage,
            actions,
            groups,
            _USAGE_PREFIX if prefix is None else prefix,
        )


def _localize_help(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Switch argparse's generated help scaffolding to Chinese."""

    parser._positionals.title = "位置参数"
    parser._optionals.title = "选项"
    parser.add_argument("-h", "--help", action="help", help=_HELP_FLAG_HELP)
    return parser


def _add_subparser(
    subparsers: argparse._SubParsersAction,
    name: str,
    **kwargs: object,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        name,
        add_help=False,
        formatter_class=_ChineseHelpFormatter,
        **kwargs,
    )
    return _localize_help(parser)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="cumt-jwxt",
        description="CUMT 教务系统命令行工具。",
        add_help=False,
        formatter_class=_ChineseHelpFormatter,
    )
    _localize_help(parser)
    parser.set_defaults(handler=_print_help, parser=parser)

    subparsers = parser.add_subparsers(dest="command")

    grades_parser = _add_subparser(subparsers, "grades", help="查询和管理成绩。")
    grades_parser.set_defaults(handler=_print_help, parser=grades_parser)
    grades_subparsers = grades_parser.add_subparsers(dest="grades_command")

    query_parser = _add_subparser(
        grades_subparsers,
        "query",
        help="查询 CUMT 教务系统成绩。",
        description="查询 CUMT 教务系统成绩。",
    )
    query_parser.add_argument(
        "--config",
        help=(
            "本地配置文件路径。默认读取当前目录或项目目录下的 "
            "config.local.json 或 config.json。"
        ),
    )
    query_parser.add_argument(
        "--year",
        help="学年起始年，例如 2024。优先于 query.auto。",
    )
    query_parser.add_argument(
        "--semester",
        help="学期代码：3 为秋季，12 为春季。优先于 query.auto。",
    )
    query_parser.add_argument(
        "--force-email",
        action="store_true",
        help="未检测到成绩变化时也发送通知邮件。",
    )
    query_parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="不使用环境变量中的代理设置。",
    )
    query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="缺少配置时直接失败，不进行交互式输入。",
    )
    query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="将成绩 JSON 保存到配置的输出目录。",
    )
    query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="将 HTML 报告保存到配置的输出目录。",
    )
    query_parser.add_argument(
        "--output-dir",
        help="可选 JSON 或报告的输出目录。",
    )
    query_parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出更详细的日志。",
    )
    query_parser.set_defaults(handler=_handle_grades_query, parser=query_parser)

    exams_parser = _add_subparser(subparsers, "exams", help="查询和管理考试安排。")
    exams_parser.set_defaults(handler=_print_help, parser=exams_parser)
    exams_subparsers = exams_parser.add_subparsers(dest="exams_command")

    exams_query_parser = _add_subparser(
        exams_subparsers,
        "query",
        help="查询 CUMT 教务系统考试安排。",
        description="查询 CUMT 教务系统考试安排。",
    )
    exams_query_parser.add_argument(
        "--config",
        help=(
            "本地配置文件路径。默认读取当前目录或项目目录下的 "
            "config.local.json 或 config.json。"
        ),
    )
    exams_query_parser.add_argument(
        "--year",
        help="学年起始年，例如 2025。优先于 query.auto。",
    )
    exams_query_parser.add_argument(
        "--semester",
        help="学期代码：3 为秋季，12 为春季。优先于 query.auto。",
    )
    exams_query_parser.add_argument(
        "--force-email",
        action="store_true",
        help="未检测到考试变化时也发送通知邮件。",
    )
    exams_query_parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="不使用环境变量中的代理设置。",
    )
    exams_query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="缺少配置时直接失败，不进行交互式输入。",
    )
    exams_query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="将考试安排 JSON 保存到配置的输出目录。",
    )
    exams_query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="将 HTML 报告保存到配置的输出目录。",
    )
    exams_query_parser.add_argument(
        "--save-ics",
        action="store_true",
        help="将 ICS 日历文件保存到配置的输出目录。",
    )
    exams_query_parser.add_argument(
        "--output-dir",
        help="可选 JSON 或报告的输出目录。",
    )
    exams_query_parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出更详细的日志。",
    )
    exams_query_parser.set_defaults(
        handler=_handle_exams_query, parser=exams_query_parser
    )

    schedule_parser = _add_subparser(
        subparsers, "schedule", help="查询和管理个人课表。"
    )
    schedule_parser.set_defaults(handler=_print_help, parser=schedule_parser)
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command")

    schedule_query_parser = _add_subparser(
        schedule_subparsers,
        "query",
        help="查询 CUMT 教务系统个人课表。",
        description="查询 CUMT 教务系统个人课表。",
    )
    schedule_query_parser.add_argument(
        "--config",
        help=(
            "本地配置文件路径。默认读取当前目录或项目目录下的 "
            "config.local.json 或 config.json。"
        ),
    )
    schedule_query_parser.add_argument(
        "--year",
        help="学年起始年，例如 2025。优先于 query.auto。",
    )
    schedule_query_parser.add_argument(
        "--semester",
        help="学期代码：3 为秋季，12 为春季。优先于 query.auto。",
    )
    schedule_query_parser.add_argument(
        "--force-email",
        action="store_true",
        help="未检测到课表变化时也发送通知邮件。",
    )
    schedule_query_parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="不使用环境变量中的代理设置。",
    )
    schedule_query_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="缺少配置时直接失败，不进行交互式输入。",
    )
    schedule_query_parser.add_argument(
        "--save-json",
        action="store_true",
        help="将课表 JSON 保存到配置的输出目录。",
    )
    schedule_query_parser.add_argument(
        "--save-report",
        action="store_true",
        help="将 HTML 报告保存到配置的输出目录。",
    )
    schedule_query_parser.add_argument(
        "--save-ics",
        action="store_true",
        help="将 ICS 日历文件保存到配置的输出目录。",
    )
    schedule_query_parser.add_argument(
        "--output-dir",
        help="可选 JSON 或报告的输出目录。",
    )
    schedule_query_parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出更详细的日志。",
    )
    schedule_query_parser.set_defaults(
        handler=_handle_schedule_query, parser=schedule_query_parser
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


def _handle_schedule_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_schedule_with_session_reuse(
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

    scope = schedule_query_scope_from_config(config.query.year, config.query.semester)
    scope_state = get_schedule_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_schedule_text_summary(
            lessons=result.lessons,
            changes=result.changes,
            year=config.query.year,
            semester=config.query.semester,
            queried_at=queried_at or "",
            period_times=result.period_times,
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
