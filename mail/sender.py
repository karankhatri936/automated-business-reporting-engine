"""SMTP email delivery for the reporting engine.

Sends the generated Excel and PDF reports as attachments.

Email is OPTIONAL:

- If ``EMAIL_ENABLED`` is not ``true`` (or SMTP details are incomplete) the
  module logs a message and returns ``False`` -- it never blocks the pipeline.
- Credentials and recipients are never hard-coded; they come from the
  environment through the application configuration.
- Delivery failures are logged and raised as ``EmailDeliveryError`` so the
  caller can decide how to continue. Generated reports are NEVER deleted.

This module only transports reports produced elsewhere; it never invents
business figures. Any summary values included in the body are supplied by
the caller (e.g. from the KPI engine).
"""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import EmailConfig, config
from ..utils.exceptions import EmailDeliveryError
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# Network timeout for SMTP connect/login/send operations.
SMTP_TIMEOUT = 30

# MIME content types for the supported report attachments.
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PDF_CONTENT_TYPE = "application/pdf"


class EmailSender:
    """Builds and sends the report email over SMTP."""

    DEFAULT_SUBJECT = "Business Report"

    def __init__(self, email_config: Optional[EmailConfig] = None) -> None:
        """
        Args:
            email_config: Optional EmailConfig; falls back to the app config.
        """
        if email_config is None:
            email_config = config.email
        self.email_config = email_config

    # ── Capability helpers ─────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """True when the user opted in AND all SMTP details are present."""
        cfg = self.email_config
        return bool(
            cfg.enabled
            and cfg.smtp_host
            and cfg.smtp_port
            and cfg.sender
            and cfg.recipient
        )

    def _validate_attachment(self, path: Path) -> None:
        """Ensure an attachment exists and is a regular file."""
        if not path.exists():
            raise EmailDeliveryError(f"Attachment not found: {path}")
        if not path.is_file():
            raise EmailDeliveryError(f"Attachment is not a file: {path}")

    # ── Message construction ────────────────────────────────────────

    def build_subject(self, report_date: Optional[str] = None) -> str:
        """Short, useful subject line, e.g. ``Business Report - 2026-09-11``."""
        report_date = report_date or datetime.now().strftime("%Y-%m-%d")
        return f"{self.DEFAULT_SUBJECT} - {report_date}"

    @staticmethod
    def _format_money(value: Any) -> str:
        try:
            return f"${float(value):,.2f}"
        except (TypeError, ValueError):
            return "-"

    def build_body(self, summary: Optional[Dict[str, Any]] = None) -> str:
        """
        Build a concise professional body.

        ``summary`` is an optional dict (typically a subset of the KPI
        results) whose values are rendered only when present.
        """
        summary = summary or {}
        report_date = summary.get("report_date") or datetime.now().strftime(
            "%Y-%m-%d"
        )
        lines = [
            "Hello,",
            "",
            "Please find the latest automated business report attached.",
            "",
            "Business report date: " + str(report_date),
        ]

        highlights = []
        total_products = summary.get("total_products")
        if total_products is not None:
            highlights.append(f"{int(total_products):,} products analyzed")
        inventory_value = summary.get("total_inventory_value")
        if inventory_value is not None:
            highlights.append(
                "total catalog inventory value (price x stock): "
                + self._format_money(inventory_value)
            )
        average_price = summary.get("average_price")
        if average_price is not None:
            highlights.append("average price: " + self._format_money(average_price))
        average_rating = summary.get("average_rating")
        if average_rating is not None:
            highlights.append(f"average rating: {float(average_rating):.2f} / 5")
        low_stock_count = summary.get("low_stock_count")
        if low_stock_count is not None:
            highlights.append(
                f"{int(low_stock_count):,} products flagged as low stock"
            )

        if highlights:
            lines.extend(["", "Summary highlights:", ""])
            lines.extend(f"- {highlight}" for highlight in highlights)

        excel_name = summary.get("excel_filename") or "Excel report"
        pdf_name = summary.get("pdf_filename") or "PDF executive summary"
        lines.extend(
            [
                "",
                "Attachments:",
                f"- {excel_name}",
                f"- {pdf_name}",
                "",
                "This email was generated automatically by the Automated "
                "Business Reporting Engine.",
            ]
        )
        return "\n".join(lines)

    def build_message(
        self,
        subject: str,
        body: str,
        attachments: List[Path],
    ) -> EmailMessage:
        """Assemble the MIME message including the report files."""
        message = EmailMessage()
        message["Subject"] = subject or self.DEFAULT_SUBJECT
        message["From"] = self.email_config.sender
        message["To"] = self.email_config.recipient
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain=self.email_config.smtp_host)
        message.set_content(body)

        for attachment in attachments:
            self._validate_attachment(attachment)
            payload = attachment.read_bytes()
            if attachment.suffix.lower() == ".pdf":
                maintype, subtype = PDF_CONTENT_TYPE.split("/", 1)
            else:
                maintype, subtype = XLSX_CONTENT_TYPE.split("/", 1)
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.name,
            )
        return message

    # ── SMTP connection ─────────────────────────────────────────────

    def _connect(self) -> smtplib.SMTP:
        """Open an SMTP connection with the appropriate TLS mode."""
        host = self.email_config.smtp_host
        port = self.email_config.smtp_port
        logger.info("Connecting to SMTP server %s:%s", host, port)
        try:
            if port == 465:
                context = ssl.create_default_context()
                return smtplib.SMTP_SSL(
                    host, port, timeout=SMTP_TIMEOUT, context=context
                )
            server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT)
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            return server
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError(
                f"Could not connect to SMTP server {host}:{port}: {exc}"
            ) from exc

    # ── Public sending API ──────────────────────────────────────────

    def send_report_email(
        self,
        excel_path: Path,
        pdf_path: Path,
        summary: Optional[Dict[str, Any]] = None,
        subject: Optional[str] = None,
    ) -> bool:
        """
        Send the Excel and PDF reports as attachments.

        Returns:
            True when the message was handed to the SMTP server.
            False when email is not enabled/configured (skipped, logged).

        Raises:
            EmailDeliveryError: On any SMTP or attachment failure. Report
                files on disk are left untouched.
        """
        if not self.is_configured:
            logger.info(
                "Email delivery skipped "
                "(EMAIL_ENABLED=%s or SMTP configuration incomplete)",
                self.email_config.enabled,
            )
            return False

        self._validate_attachment(excel_path)
        self._validate_attachment(pdf_path)

        report_date = summary.get("report_date") if summary else None
        message = self.build_message(
            subject or self.build_subject(report_date),
            self.build_body(summary),
            [excel_path, pdf_path],
        )

        try:
            with self._connect() as server:
                server.login(self.email_config.sender, self.email_config.password)
                server.send_message(message)
            logger.info(
                "Email with %d attachment(s) sent to %s",
                len(message.get_payload()) - 1,
                self.email_config.recipient,
            )
            return True
        except EmailDeliveryError:
            raise
        except (smtplib.SMTPException, OSError) as exc:
            logger.exception("Email delivery failed: %s", exc)
            raise EmailDeliveryError(f"Email delivery failed: {exc}") from exc


def send_report_email(
    excel_path: Path,
    pdf_path: Path,
    summary: Optional[Dict[str, Any]] = None,
    subject: Optional[str] = None,
    email_config: Optional[EmailConfig] = None,
) -> bool:
    """
    Convenience wrapper around :class:`EmailSender`.

    Email never blocks the reporting pipeline: failures raise
    ``EmailDeliveryError`` and skipped/delivered states are returned as bool.
    """
    sender = EmailSender(email_config=email_config)
    return sender.send_report_email(
        excel_path, pdf_path, summary=summary, subject=subject
    )