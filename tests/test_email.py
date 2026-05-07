"""Email notification tests."""

import smtplib
import socket

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.models import NotifyConfig
from cumt_jwxt_cli.notify.email import send_grade_email


class _SMTP:
    instances: list["_SMTP"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logged_in: tuple[str, str] | None = None
        self.messages: list[object] = []
        _SMTP.instances.append(self)

    def __enter__(self) -> "_SMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message: object) -> None:
        self.messages.append(message)


def _config(**overrides: object) -> NotifyConfig:
    values = {
        "enabled": True,
        "smtp_host": "smtp.example.test",
        "smtp_port": 465,
        "username": "sender-user",
        "password": "sender-password",
        "sender": "sender@example.test",
        "recipients": ("a@example.test", "b@example.test"),
    }
    values.update(overrides)
    return NotifyConfig(**values)


def test_send_grade_email_sends_html_message() -> None:
    _SMTP.instances.clear()

    send_grade_email(
        _config(),
        subject="Grades changed",
        text_body="plain",
        html_body="<p>html</p>",
        smtp_factory=_SMTP,
    )

    smtp = _SMTP.instances[0]
    assert smtp.host == "smtp.example.test"
    assert smtp.logged_in == ("sender-user", "sender-password")
    assert len(smtp.messages) == 1


def test_send_grade_email_skips_disabled_notify() -> None:
    _SMTP.instances.clear()

    send_grade_email(
        _config(enabled=False),
        subject="Grades changed",
        text_body="plain",
        html_body="<p>html</p>",
        smtp_factory=_SMTP,
    )

    assert _SMTP.instances == []


def test_send_grade_email_rejects_incomplete_config() -> None:
    with pytest.raises(NotifyError, match="notify.smtp_host"):
        send_grade_email(
            _config(smtp_host=""),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=_SMTP,
        )


def test_send_grade_email_reports_smtp_authentication_failure() -> None:
    class AuthFailedSMTP(_SMTP):
        def login(self, username: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    with pytest.raises(NotifyError, match="SMTP authentication failed"):
        send_grade_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=AuthFailedSMTP,
        )


def test_send_grade_email_reports_smtp_connection_failure() -> None:
    def fail_connect(host: str, port: int, timeout: float) -> object:
        raise TimeoutError("connect timed out")

    with pytest.raises(NotifyError, match="SMTP connection failed"):
        send_grade_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=fail_connect,
        )


def test_send_grade_email_reports_smtp_send_failure() -> None:
    class SendFailedSMTP(_SMTP):
        def send_message(self, message: object) -> None:
            raise smtplib.SMTPRecipientsRefused(
                {"user@example.test": (550, b"rejected")}
            )

    with pytest.raises(NotifyError, match="SMTP send failed"):
        send_grade_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=SendFailedSMTP,
        )


def test_send_grade_email_reports_socket_failure() -> None:
    def fail_connect(host: str, port: int, timeout: float) -> object:
        raise socket.gaierror("name lookup failed")

    with pytest.raises(NotifyError, match="SMTP connection failed"):
        send_grade_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=fail_connect,
        )
