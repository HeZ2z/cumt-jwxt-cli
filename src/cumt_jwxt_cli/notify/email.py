"""Email notification delivery."""

from __future__ import annotations

import smtplib
import socket
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formataddr

from cumt_jwxt_cli.errors import NotifyError
from cumt_jwxt_cli.models import NotifyConfig


def send_grade_email(
    config: NotifyConfig,
    *,
    subject: str,
    text_body: str,
    html_body: str,
    smtp_factory: Callable[..., object] = smtplib.SMTP_SSL,
    timeout_seconds: float = 30.0,
) -> None:
    """Send a grade notification email when notification is enabled."""

    if not config.enabled:
        return
    _validate_config(config)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        formataddr((config.sender_name, config.sender))
        if config.sender_name
        else config.sender
    )
    message["To"] = ", ".join(config.recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtp_factory(
            config.smtp_host,
            config.smtp_port,
            timeout=timeout_seconds,
        ) as smtp:
            smtp.login(config.username, config.password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise NotifyError(
            "SMTP authentication failed. Check notify.username, "
            "notify.password, and server auth settings."
        ) from exc
    except (
        TimeoutError,
        socket.gaierror,
        ConnectionError,
        smtplib.SMTPConnectError,
        smtplib.SMTPServerDisconnected,
    ) as exc:
        raise NotifyError(
            "SMTP connection failed. Check notify.smtp_host, notify.smtp_port, "
            "network reachability, and TLS settings."
        ) from exc
    except (
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPSenderRefused,
        smtplib.SMTPDataError,
        smtplib.SMTPResponseException,
    ) as exc:
        raise NotifyError(
            "SMTP send failed. Check sender/recipient addresses and server policy."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - smtplib exposes several failures.
        raise NotifyError(
            "Email notification failed due to an unexpected SMTP error."
        ) from exc


def _validate_config(config: NotifyConfig) -> None:
    required_fields = {
        "notify.smtp_host": config.smtp_host,
        "notify.username": config.username,
        "notify.password": config.password,
        "notify.sender": config.sender,
    }
    missing = [name for name, value in required_fields.items() if not value]
    if not config.recipients:
        missing.append("notify.recipients")
    if missing:
        raise NotifyError(
            "Missing email notification configuration: " + ", ".join(missing)
        )
