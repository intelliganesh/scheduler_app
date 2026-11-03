"""SMTP delivery for generated job reports using Python's standard library."""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from app.config.settings import get_settings
from app.schemas.workflow import EMAIL_PATTERN


def send_report(job_title: str, recipients: list[str], storage_path: str) -> bool:
    settings = get_settings()
    if not settings.smtp_enabled or not recipients:
        return False
    path = Path(storage_path)
    return send_report_content(job_title, recipients, path.name, path.read_bytes(), path.suffix.lower())


def send_report_content(job_title: str, recipients: list[str], filename: str, content: bytes, suffix: str = ".csv") -> bool:
    settings = get_settings()
    if not settings.smtp_enabled or not recipients:
        return False
    if not settings.smtp_host.strip() or not EMAIL_PATTERN.fullmatch(settings.smtp_from_email):
        raise ValueError("Set SMTP_HOST and a valid SMTP_FROM_EMAIL before enabling email delivery.")
    if settings.smtp_start_tls and settings.smtp_use_ssl:
        raise ValueError("Enable either SMTP_START_TLS or SMTP_USE_SSL, not both.")
    if not 1 <= settings.smtp_port <= 65535 or settings.smtp_timeout_seconds <= 0:
        raise ValueError("SMTP_PORT and SMTP_TIMEOUT_SECONDS must be valid positive values.")
    if bool(settings.smtp_username) != bool(settings.smtp_password):
        raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both blank for a relay.")
    if any(not EMAIL_PATTERN.fullmatch(address) for address in recipients):
        raise ValueError("The job contains an invalid email recipient. Edit its recipients before retrying.")
    message = EmailMessage()
    message["Subject"] = "Report: " + " ".join(job_title.splitlines())
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = ", ".join(recipients)
    message.set_content(f"The generated report for {job_title} is attached.\n")
    maintype, subtype = ("application", "zip") if suffix.lower() == ".zip" else ("text", "csv")
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    context = ssl.create_default_context()
    transport = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    kwargs = {"timeout": settings.smtp_timeout_seconds}
    if settings.smtp_use_ssl:
        kwargs["context"] = context
    try:
        with transport(settings.smtp_host, settings.smtp_port, **kwargs) as smtp:
            if settings.smtp_start_tls:
                smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            refused = smtp.send_message(message, from_addr=settings.smtp_from_email, to_addrs=recipients)
            if refused:
                raise ValueError("The mail server rejected one or more recipients. Check job recipients before retrying.")
    except (smtplib.SMTPException, OSError) as exc:
        raise ValueError("SMTP delivery failed. Check the SMTP settings and mail server connection, then retry the run.") from exc
    return True
