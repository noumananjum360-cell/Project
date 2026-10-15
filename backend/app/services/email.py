"""Outbound email. Uses SMTP when configured.

When SMTP is not configured, messages are NOT sent. In development and test
the action link is written to the server log so the flow can be exercised
locally; in production the absence of SMTP is logged as a warning only.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Captured messages for automated tests (test environment only).
OUTBOX: list[dict[str, str]] = []


def email_configured() -> bool:
    return bool(get_settings().SMTP_HOST)


def send_email(to: str, subject: str, body: str, *, dev_link: str | None = None) -> bool:
    settings = get_settings()
    if settings.ENVIRONMENT == "test":
        OUTBOX.append({"to": to, "subject": subject, "body": body, "link": dev_link or ""})
        return True
    if not settings.SMTP_HOST:
        if settings.is_production:
            log.warning("email_not_configured", subject=subject)
        else:
            log.info("dev_email_not_sent", subject=subject, dev_link=dev_link)
        return False
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error("email_send_failed", error_type=type(exc).__name__)
        return False
