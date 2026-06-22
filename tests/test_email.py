"""Email notification tests."""

import smtplib
import socket

import pytest

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.models import NotifyConfig
from cumt_jwxt_cli.notify.email import send_email


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
        "sender_name": "",
        "recipients": ("a@example.test", "b@example.test"),
    }
    values.update(overrides)
    return NotifyConfig(**values)


def test_send_email_sends_html_message() -> None:
    _SMTP.instances.clear()

    send_email(
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


def test_send_email_uses_sender_display_name_when_configured() -> None:
    _SMTP.instances.clear()

    send_email(
        _config(sender_name="cumt-jwxt-cli"),
        subject="Grades changed",
        text_body="plain",
        html_body="<p>html</p>",
        smtp_factory=_SMTP,
    )

    smtp = _SMTP.instances[0]
    message = smtp.messages[0]
    assert message["From"] == "cumt-jwxt-cli <sender@example.test>"


def test_send_email_skips_disabled_notify() -> None:
    _SMTP.instances.clear()

    send_email(
        _config(enabled=False),
        subject="Grades changed",
        text_body="plain",
        html_body="<p>html</p>",
        smtp_factory=_SMTP,
    )

    assert _SMTP.instances == []


def test_send_email_rejects_incomplete_config() -> None:
    with pytest.raises(NotifyError, match="notify.smtp_host"):
        send_email(
            _config(smtp_host=""),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=_SMTP,
        )


def test_send_email_reports_smtp_authentication_failure() -> None:
    class AuthFailedSMTP(_SMTP):
        def login(self, username: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    with pytest.raises(NotifyError, match="SMTP authentication failed"):
        send_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=AuthFailedSMTP,
        )


def test_send_email_reports_smtp_connection_failure() -> None:
    def fail_connect(host: str, port: int, timeout: float) -> object:
        raise TimeoutError("connect timed out")

    with pytest.raises(NotifyError, match="SMTP connection failed"):
        send_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=fail_connect,
        )


def test_send_email_reports_smtp_send_failure() -> None:
    class SendFailedSMTP(_SMTP):
        def send_message(self, message: object) -> None:
            raise smtplib.SMTPRecipientsRefused(
                {"user@example.test": (550, b"rejected")}
            )

    with pytest.raises(NotifyError, match="SMTP send failed"):
        send_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=SendFailedSMTP,
        )


def test_send_email_reports_socket_failure() -> None:
    def fail_connect(host: str, port: int, timeout: float) -> object:
        raise socket.gaierror("name lookup failed")

    with pytest.raises(NotifyError, match="SMTP connection failed"):
        send_email(
            _config(),
            subject="Grades changed",
            text_body="plain",
            html_body="<p>html</p>",
            smtp_factory=fail_connect,
        )


def test_send_email_with_attachment() -> None:
    _SMTP.instances.clear()

    send_email(
        _config(),
        subject="With attachment",
        text_body="plain",
        html_body="<p>html</p>",
        attachments=[("exam.ics", b"BEGIN:VCALENDAR", "text/calendar")],
        smtp_factory=_SMTP,
    )

    smtp = _SMTP.instances[0]
    assert len(smtp.messages) == 1
    message = smtp.messages[0]
    assert "With attachment" in message["Subject"]
    assert message.is_multipart()
    for part in message.walk():
        if part.get_filename() == "exam.ics":
            assert part.get_content_type() == "text/calendar"
            assert part.get_payload(decode=True) == b"BEGIN:VCALENDAR"
            break
    else:
        pytest.fail("attachment not found in message")


def test_send_email_with_multiple_attachments() -> None:
    _SMTP.instances.clear()

    send_email(
        _config(),
        subject="Multiple attachments",
        text_body="plain",
        html_body="<p>html</p>",
        attachments=[
            ("exam.ics", b"BEGIN:VCALENDAR", "text/calendar"),
            ("notes.txt", b"hello", "text/plain"),
        ],
        smtp_factory=_SMTP,
    )

    smtp = _SMTP.instances[0]
    message = smtp.messages[0]
    filenames = []
    for part in message.walk():
        fn = part.get_filename()
        if fn:
            filenames.append(fn)
    assert "exam.ics" in filenames
    assert "notes.txt" in filenames


def test_send_email_attachments_ignored_when_none() -> None:
    _SMTP.instances.clear()

    send_email(
        _config(),
        subject="No attachments",
        text_body="plain",
        html_body="<p>html</p>",
        attachments=None,
        smtp_factory=_SMTP,
    )

    smtp = _SMTP.instances[0]
    message = smtp.messages[0]
    for part in message.walk():
        assert part.get_filename() is None
