"""Email delivery for the reporting engine."""

from .sender import EmailSender, send_report_email

__all__ = ["EmailSender", "send_report_email"]
