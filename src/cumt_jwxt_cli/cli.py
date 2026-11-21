"""Command line interface for cumt-jwxt-cli."""

import argparse
import re
import sys
from collections.abc import Sequence

from cumt_jwxt_cli.academic.report import build_academic_text_summary
from cumt_jwxt_cli.app import (
    query_academic_with_session_reuse,
    query_classrooms_with_session_reuse,
    query_courses_with_session_reuse,
    query_exams_with_session_reuse,
    query_grades_with_session_reuse,
    query_schedule_with_session_reuse,
)
from cumt_jwxt_cli.classrooms.query_fetch import (
    ClassroomQueryOptions,
    parse_clock,
    parse_date,
)
from cumt_jwxt_cli.classrooms.report import build_classrooms_text_summary
from cumt_jwxt_cli.config import load_app_config
from cumt_jwxt_cli.courses.query_fetch import (
    MAX_RESULTS as MAX_COURSE_RESULTS,
)
from cumt_jwxt_cli.courses.query_fetch import CourseQueryOptions
from cumt_jwxt_cli.courses.report import build_courses_text_summary
from cumt_jwxt_cli.errors import (
    AuthError,
    CaptchaError,
    ConfigError,
    CUMTJWXTError,
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
from cumt_jwxt_cli.state import state_lock

_USAGE_PREFIX = "用法: "
_HELP_FLAG_HELP = "显示帮助信息并退出。"
_PERIODS_PATTERN = re.compile(r"^\d+(-\d+)?$")


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


def _add_query_arguments(
    parser: argparse.ArgumentParser,
    *,
    target: str,
    save_ics: bool = False,
    include_force_email: bool = True,
    include_output: bool = True,
    include_scope: bool = True,
) -> None:
    """Add the flags shared by every query subcommand."""

    parser.add_argument(
        "--config",
        help=(
            "本地配置文件路径。默认读取当前目录或项目目录下的 "
            "config.local.json 或 config.json。"
        ),
    )
    if include_scope:
        parser.add_argument("--year", help="学年起始年，例如 2025。优先于 query.auto。")
        parser.add_argument(
            "--semester", help="学期代码：3 为秋季，12 为春季。优先于 query.auto。"
        )
    if include_force_email:
        parser.add_argument(
            "--force-email",
            action="store_true",
            help=f"未检测到{target}变化时也发送通知邮件。",
        )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="不使用环境变量中的代理设置。",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="缺少配置时直接失败，不进行交互式输入。",
    )
    if include_output:
        parser.add_argument(
            "--save-json",
            action="store_true",
            help=f"将{target} JSON 保存到配置的输出目录。",
        )
        parser.add_argument(
            "--save-report",
            action="store_true",
            help="将 HTML 报告保存到配置的输出目录。",
        )
        if save_ics:
            parser.add_argument(
                "--save-ics",
                action="store_true",
                help="将 ICS 日历文件保存到配置的输出目录。",
            )
        parser.add_argument("--output-dir", help="可选 JSON 或报告的输出目录。")
    parser.add_argument("--verbose", action="store_true", help="输出更详细的日志。")


def _date_arg(value: str) -> str:
    try:
        return parse_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _clock_arg(value: str) -> str:
    try:
        return parse_clock(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"必须为整数: {value}") from exc
    if number < 0:
        raise argparse.ArgumentTypeError(f"必须为非负整数: {value}")
    return number


def _weekday_arg(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"星期必须为 1-7: {value}") from exc
    if not 1 <= number <= 7:
        raise argparse.ArgumentTypeError(f"星期必须为 1-7: {value}")
    return number


def _periods_arg(value: str) -> str:
    if _PERIODS_PATTERN.match(value) is None:
        raise argparse.ArgumentTypeError(f"节次格式应形如 1-2: {value}")
    return value


def _course_limit_arg(value: str) -> int:
    number = _non_negative_int(value)
    if number > MAX_COURSE_RESULTS:
        raise argparse.ArgumentTypeError(f"上限为 {MAX_COURSE_RESULTS}: {value}")
    return number


def _add_course_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--course", help="课程号或课程 ID。")
    parser.add_argument("--teacher", help="教师姓名。")
    parser.add_argument("--room", help="上课场地，例如 博1-A203。")
    parser.add_argument("--weekday", type=_weekday_arg, help="星期，1-7。")
    parser.add_argument("--periods", type=_periods_arg, help="上课节次，例如 1-2。")
    parser.add_argument("--weeks", help="起始周，例如 1。")
    parser.add_argument(
        "--limit",
        type=_course_limit_arg,
        default=50,
        help=f"最多显示多少条；0 表示全部（上限 {MAX_COURSE_RESULTS}）。",
    )


def _add_classroom_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        required=True,
        type=_date_arg,
        help="查询日期，格式 YYYY-MM-DD。",
    )
    parser.add_argument("--start", type=_clock_arg, help="起始时刻，格式 HH:MM。")
    parser.add_argument("--end", type=_clock_arg, help="结束时刻，格式 HH:MM。")
    parser.add_argument(
        "--campus",
        choices=("all", "nanhu", "wenchang"),
        default="all",
        help="校区：all 全部、nanhu 南湖、wenchang 文昌。",
    )
    parser.add_argument("--building", default="", help="楼号，例如 博1。")
    parser.add_argument("--min-seats", type=_non_negative_int, help="最小座位数。")
    parser.add_argument("--max-seats", type=_non_negative_int, help="最大座位数。")
    parser.add_argument("--lendable", action="store_true", help="仅显示可借用教室。")
    parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=50,
        help="最多显示多少间；0 表示全部（上限 5000）。",
    )


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
    _add_query_arguments(query_parser, target="成绩")
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
    _add_query_arguments(exams_query_parser, target="考试安排", save_ics=True)
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
    _add_query_arguments(schedule_query_parser, target="课表", save_ics=True)
    schedule_query_parser.set_defaults(
        handler=_handle_schedule_query, parser=schedule_query_parser
    )

    classrooms_parser = _add_subparser(subparsers, "classrooms", help="查询空闲教室。")
    classrooms_parser.set_defaults(handler=_print_help, parser=classrooms_parser)
    classrooms_subparsers = classrooms_parser.add_subparsers(dest="classrooms_command")

    classrooms_query_parser = _add_subparser(
        classrooms_subparsers,
        "query",
        help="查询 CUMT 教务系统空闲教室。",
        description="查询 CUMT 教务系统空闲教室。",
    )
    _add_query_arguments(
        classrooms_query_parser,
        target="空闲教室",
        include_force_email=False,
        include_output=False,
    )
    _add_classroom_arguments(classrooms_query_parser)
    classrooms_query_parser.set_defaults(
        handler=_handle_classrooms_query, parser=classrooms_query_parser
    )

    academic_parser = _add_subparser(subparsers, "academic", help="查询学业情况。")
    academic_parser.set_defaults(handler=_print_help, parser=academic_parser)
    academic_subparsers = academic_parser.add_subparsers(dest="academic_command")

    academic_query_parser = _add_subparser(
        academic_subparsers,
        "query",
        help="查询 CUMT 教务系统学业情况。",
        description="查询 CUMT 教务系统学业情况。",
    )
    _add_query_arguments(
        academic_query_parser,
        target="学业情况",
        include_force_email=False,
        include_output=False,
        include_scope=False,
    )
    academic_query_parser.set_defaults(
        handler=_handle_academic_query, parser=academic_query_parser
    )

    courses_parser = _add_subparser(subparsers, "courses", help="按条件查询上课情况。")
    courses_parser.set_defaults(handler=_print_help, parser=courses_parser)
    courses_subparsers = courses_parser.add_subparsers(dest="courses_command")

    courses_query_parser = _add_subparser(
        courses_subparsers,
        "query",
        help="按课程、教师或场地查询 CUMT 教务系统上课情况。",
        description="按课程、教师或场地查询 CUMT 教务系统上课情况。",
    )
    _add_query_arguments(
        courses_query_parser,
        target="上课情况",
        include_force_email=False,
        include_output=False,
        include_scope=True,
    )
    _add_course_arguments(courses_query_parser)
    courses_query_parser.set_defaults(
        handler=_handle_courses_query, parser=courses_query_parser
    )

    return parser


def _print_help(args: argparse.Namespace) -> int:
    args.parser.print_help()
    return int(ExitCode.OK)


def _exit_code_for(exc: CUMTJWXTError) -> ExitCode:
    if isinstance(exc, ConfigError):
        return ExitCode.CONFIG_ERROR
    if isinstance(exc, (AuthError, CaptchaError)):
        return ExitCode.AUTH_ERROR
    if isinstance(exc, QueryError):
        return ExitCode.QUERY_ERROR
    if isinstance(exc, ParseError):
        return ExitCode.PARSE_ERROR
    if isinstance(exc, NotifyError):
        return ExitCode.NOTIFY_ERROR
    if isinstance(exc, (SnapshotError, StateError)):
        return ExitCode.UNKNOWN
    return ExitCode.UNKNOWN


def _handle_grades_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        with state_lock(config):
            result = query_grades_with_session_reuse(
                config,
                force_email=args.force_email,
                trust_env=not args.no_proxy,
                allow_manual_captcha=not args.no_interactive,
            )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    scope = grade_query_scope_from_config(result.year, result.semester)
    scope_state = get_grade_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_text_summary(
            grades=result.grades,
            changes=result.changes,
            year=result.year,
            semester=result.semester,
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
        with state_lock(config):
            result = query_exams_with_session_reuse(
                config,
                force_email=args.force_email,
                trust_env=not args.no_proxy,
                allow_manual_captcha=not args.no_interactive,
            )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    scope = exam_query_scope_from_config(result.year, result.semester)
    scope_state = get_exam_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_exam_text_summary(
            exams=result.exams,
            changes=result.changes,
            year=result.year,
            semester=result.semester,
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
        with state_lock(config):
            result = query_schedule_with_session_reuse(
                config,
                force_email=args.force_email,
                trust_env=not args.no_proxy,
                allow_manual_captcha=not args.no_interactive,
            )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    scope = schedule_query_scope_from_config(result.year, result.semester)
    scope_state = get_schedule_query_state(result.state, scope)
    queried_at = (
        "" if scope_state is None else scope_state.last_successful_query_at or ""
    )
    print(
        build_schedule_text_summary(
            lessons=result.lessons,
            changes=result.changes,
            year=result.year,
            semester=result.semester,
            queried_at=queried_at or "",
            period_times=result.period_times,
        )
    )
    return int(ExitCode.OK)


def _handle_classrooms_query(args: argparse.Namespace) -> int:
    if (args.start is None) != (args.end is None):
        args.parser.error("--start 和 --end 必须同时提供或同时省略。")
    if args.start and args.end and args.start > args.end:
        args.parser.error("--start 不能晚于 --end。")
    if (
        args.min_seats is not None
        and args.max_seats is not None
        and args.min_seats > args.max_seats
    ):
        args.parser.error("--min-seats 不能大于 --max-seats。")

    options = ClassroomQueryOptions(
        date=args.date,
        start=args.start,
        end=args.end,
        campus=args.campus,
        building=args.building,
        min_seats=args.min_seats,
        max_seats=args.max_seats,
        lendable=args.lendable,
        limit=args.limit,
    )

    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_classrooms_with_session_reuse(
            config,
            options=options,
            trust_env=not args.no_proxy,
            allow_manual_captcha=not args.no_interactive,
        )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    print(
        build_classrooms_text_summary(
            classrooms=result.classrooms,
            total=result.total,
            date=args.date,
            start=args.start,
            end=args.end,
            campus=args.campus,
        )
    )
    return int(ExitCode.OK)


def _handle_courses_query(args: argparse.Namespace) -> int:
    if not (args.course or args.teacher or args.room):
        # Pulling the whole teaching plan is over 10k rows, so require at least
        # one server-side filter instead of fetching everything.
        args.parser.error("必须至少提供 --course、--teacher 或 --room 之一。")

    options = CourseQueryOptions(
        course=args.course,
        teacher=args.teacher,
        room=args.room,
        weekday=args.weekday,
        periods=args.periods,
        weeks=args.weeks,
        limit=args.limit,
    )

    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_courses_with_session_reuse(
            config,
            options=options,
            trust_env=not args.no_proxy,
            allow_manual_captcha=not args.no_interactive,
        )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    print(
        build_courses_text_summary(
            sessions=result.sessions,
            total=result.total,
            year=result.year,
            semester=result.semester,
            course=args.course,
            teacher=args.teacher,
            room=args.room,
            weekday=args.weekday,
            periods=args.periods,
            weeks=args.weeks,
        )
    )
    return int(ExitCode.OK)


def _handle_academic_query(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args)
        configure_logging(
            config_path=config.config_path,
            retention_days=config.logging.retention_days,
            verbose=args.verbose,
        )
        result = query_academic_with_session_reuse(
            config,
            trust_env=not args.no_proxy,
            allow_manual_captcha=not args.no_interactive,
        )
    except CUMTJWXTError as exc:
        print(str(exc), file=sys.stderr)
        return int(_exit_code_for(exc))

    print(build_academic_text_summary(result))
    return int(ExitCode.OK)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "parser"):
        args.parser = parser
    return args.handler(args)
