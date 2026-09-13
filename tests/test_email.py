"""Tests for SMTP email delivery (fully mocked - no real SMTP server)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import smtplib

from automated_business_reporting_engine.config import EmailConfig
from automated_business_reporting_engine.mail.sender import (
    EmailSender,
    XLSX_CONTENT_TYPE,
    send_report_email,
)
from automated_business_reporting_engine.utils.exceptions import EmailDeliveryError


def _email_config(**overrides):
    """Build a fully configured EmailConfig for tests."""
    defaults = {
        "enabled": True,
        "smtp_host": "smtp.test.example.com",
        "smtp_port": 587,
        "sender": "sender@example.com",
        "recipient": "recipient@example.com",
        "password": "test-app-password",
    }
    defaults.update(overrides)
    return EmailConfig(**defaults)


def _make_smtp_server():
    """A MagicMock SMTP whose context manager returns itself (like smtplib)."""
    server = MagicMock()
    server.__enter__.return_value = server
    return server


class TestEmailSender(unittest.TestCase):
    """Test suite for EmailSender."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        self.temp = Path(self.temp_dir.name)
        self.excel_path = self.temp / "Business_Report_2026-09-11.xlsx"
        self.pdf_path = self.temp / "Business_Report_2026-09-11.pdf"
        self.excel_path.write_bytes(b"PK\x03\x04 fake excel bytes")
        self.pdf_path.write_bytes(b"%PDF- fake pdf bytes")

        self.sender = EmailSender(email_config=_email_config())
        self.summary = {
            "report_date": "2026-09-11",
            "total_products": 5,
            "total_inventory_value": 1234.56,
            "average_price": 20.0,
            "average_rating": 4.2,
            "low_stock_count": 1,
            "excel_filename": self.excel_path.name,
            "pdf_filename": self.pdf_path.name,
        }

    def test_skipped_when_disabled(self):
        """Disabled email returns False without touching SMTP."""
        sender = EmailSender(email_config=_email_config(enabled=False))
        with patch(
            "automated_business_reporting_engine.mail.sender.smtplib.SMTP"
        ) as mock_smtp:
            result = sender.send_report_email(self.excel_path, self.pdf_path)
        self.assertFalse(result)
        mock_smtp.assert_not_called()

    def test_message_contains_both_attachments(self):
        """The built message attaches the PDF and Excel files."""
        subject = self.sender.build_subject("2026-09-11")
        message = self.sender.build_message(
            subject, self.sender.build_body(self.summary),
            [self.excel_path, self.pdf_path],
        )

        names = [att.get_filename() for att in message.iter_attachments()]
        self.assertIn(self.excel_path.name, names)
        self.assertIn(self.pdf_path.name, names)

        excel_att = next(
            att for att in message.iter_attachments()
            if att.get_filename() == self.excel_path.name
        )
        self.assertEqual(excel_att.get_content_type(), XLSX_CONTENT_TYPE)
        self.assertEqual(
            excel_att.get_payload(decode=True), b"PK\x03\x04 fake excel bytes"
        )

    def test_body_contains_real_summary_values(self):
        """Body renders meaningful, real values from the summary dict."""
        body = self.sender.build_body(self.summary)
        self.assertIn("5 products analyzed", body)
        self.assertIn("$1,234.56", body)
        self.assertIn("4.20 / 5", body)
        self.assertIn(self.excel_path.name, body)
        self.assertIn(self.pdf_path.name, body)

    def test_subject_contains_report_date(self):
        self.assertEqual(
            self.sender.build_subject("2026-09-11"), "Business Report - 2026-09-11"
        )

    def test_send_success(self):
        """A successful send logs in, sends, and returns True."""
        with patch(
            "automated_business_reporting_engine.mail.sender.smtplib.SMTP"
        ) as mock_smtp:
            mock_server = _make_smtp_server()
            mock_server.has_extn.return_value = True
            mock_smtp.return_value = mock_server

            result = self.sender.send_report_email(
                self.excel_path, self.pdf_path, summary=self.summary
            )

        self.assertTrue(result)
        mock_smtp.assert_called_once()
        mock_server.login.assert_called_once_with(
            "sender@example.com", "test-app-password"
        )
        mock_server.send_message.assert_called_once()
        mock_server.starttls.assert_called_once()

    def test_send_failure_raises_and_logs(self):
        """SMTP failures surface as EmailDeliveryError (pipeline can continue)."""
        with patch(
            "automated_business_reporting_engine.mail.sender.smtplib.SMTP"
        ) as mock_smtp:
            mock_server = _make_smtp_server()
            mock_smtp.return_value = mock_server
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b"Authentication failed"
            )

            with self.assertRaises(EmailDeliveryError):
                self.sender.send_report_email(
                    self.excel_path, self.pdf_path, summary=self.summary
                )

    def test_missing_attachment_raises(self):
        """A missing report file prevents sending and raises EmailDeliveryError."""
        missing = self.temp / "does_not_exist.pdf"
        with self.assertRaises(EmailDeliveryError):
            self.sender.send_report_email(self.excel_path, missing)

    def test_convenience_function_returns_bool(self):
        """Module-level send_report_email delegates to EmailSender."""
        with patch(
            "automated_business_reporting_engine.mail.sender.smtplib.SMTP"
        ) as mock_smtp:
            mock_server = _make_smtp_server()
            mock_smtp.return_value = mock_server
            result = send_report_email(
                self.excel_path,
                self.pdf_path,
                summary=self.summary,
                email_config=_email_config(),
            )
        self.assertTrue(result)
        mock_server.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()