import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.settings import Settings
from app.services.email_service import send_report


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "report.csv"
        self.path.write_bytes(b"name,total\nDemo,100\n")
        self.settings = Settings(_env_file=None, smtp_enabled=True, smtp_host="smtp.example.com",
                                 smtp_username="sender", smtp_password="test-password", smtp_from_email="reports@example.com")
        patcher = patch("app.services.email_service.get_settings", return_value=self.settings)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_starttls_authentication_and_csv_attachment(self):
        with patch("app.services.email_service.smtplib.SMTP") as transport:
            smtp = transport.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            self.assertTrue(send_report("Payroll", ["receiver@example.com"], str(self.path)))
            transport.assert_called_once_with("smtp.example.com", 587, timeout=30)
            smtp.starttls.assert_called_once()
            smtp.login.assert_called_once_with("sender", "test-password")
            message = smtp.send_message.call_args.args[0]
            self.assertEqual(message["Subject"], "Report: Payroll")
            attachment = list(message.iter_attachments())[0]
            self.assertEqual(attachment.get_filename(), "report.csv")
            self.assertEqual(attachment.get_payload(decode=True), self.path.read_bytes())
            self.assertEqual(attachment.get_content_type(), "text/csv")

    def test_ssl_relay_and_zip_attachment(self):
        self.settings.smtp_use_ssl = True
        self.settings.smtp_start_tls = False
        self.settings.smtp_port = 465
        self.settings.smtp_username = self.settings.smtp_password = ""
        archive = self.path.with_suffix(".zip")
        archive.write_bytes(b"test archive")
        with patch("app.services.email_service.smtplib.SMTP_SSL") as transport:
            smtp = transport.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            self.assertTrue(send_report("Split", ["receiver@example.com"], str(archive)))
            smtp.starttls.assert_not_called()
            smtp.login.assert_not_called()
            self.assertEqual(list(smtp.send_message.call_args.args[0].iter_attachments())[0].get_content_type(), "application/zip")

    def test_disabled_or_empty_recipients_do_not_connect(self):
        with patch("app.services.email_service.smtplib.SMTP") as transport:
            self.settings.smtp_enabled = False
            self.assertFalse(send_report("Payroll", ["receiver@example.com"], "missing.csv"))
            self.settings.smtp_enabled = True
            self.assertFalse(send_report("Payroll", [], "missing.csv"))
            transport.assert_not_called()

    def test_invalid_configuration_and_recipient_are_rejected_before_connection(self):
        for changes in ({"smtp_host": ""}, {"smtp_from_email": "bad"}, {"smtp_use_ssl": True},
                        {"smtp_port": 0}, {"smtp_timeout_seconds": 0}, {"smtp_password": ""}):
            original = self.settings.model_copy()
            for key, value in changes.items(): setattr(self.settings, key, value)
            with patch("app.services.email_service.smtplib.SMTP") as transport:
                with self.assertRaises(ValueError):
                    send_report("Payroll", ["receiver@example.com"], str(self.path))
                transport.assert_not_called()
            self.settings.__dict__.update(original.__dict__)
        with self.assertRaises(ValueError):
            send_report("Payroll", ["receiver@example.com\r\nBcc: other@example.com"], str(self.path))

    def test_transport_failure_is_sanitized_and_partial_refusal_is_not_success(self):
        with patch("app.services.email_service.smtplib.SMTP", side_effect=OSError("private server detail")):
            with self.assertRaisesRegex(ValueError, "SMTP delivery failed") as error:
                send_report("Payroll", ["receiver@example.com"], str(self.path))
            self.assertNotIn("private server detail", str(error.exception))
        with patch("app.services.email_service.smtplib.SMTP") as transport:
            smtp = transport.return_value.__enter__.return_value
            smtp.send_message.return_value = {"receiver@example.com": (550, b"rejected")}
            with self.assertRaisesRegex(ValueError, "rejected"):
                send_report("Payroll", ["receiver@example.com"], str(self.path))
