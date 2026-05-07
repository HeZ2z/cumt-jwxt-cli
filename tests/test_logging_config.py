"""Logging setup tests."""

import logging

from cumt_jwxt_cli.logging_config import SensitiveDataFilter, configure_logging


def test_sensitive_data_filter_redacts_known_secret_patterns() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "password=secret api_key=abc JSESSIONID=session route=node "
            "Cookie: JSESSIONID=session; route=node"
        ),
        args=(),
        exc_info=None,
    )

    SensitiveDataFilter().filter(record)

    assert "secret" not in record.msg
    assert "abc" not in record.msg
    assert "session" not in record.msg
    assert "node" not in record.msg
    assert "Cookie: ***" in record.msg
    assert "***" in record.msg


def test_configure_logging_creates_config_adjacent_log_file(tmp_path) -> None:
    config_path = tmp_path / "config.local.json"

    configure_logging(config_path=config_path, retention_days=14, verbose=False)

    assert (tmp_path / "logs").is_dir()
    assert list((tmp_path / "logs").glob("cumt-jwxt-*.log"))
