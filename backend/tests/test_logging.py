import logging
import tempfile
import unittest
from pathlib import Path

from app.config.logging import configure_logging


class LoggingConfigurationTests(unittest.TestCase):
    def test_all_components_write_one_formatted_file(self):
        with tempfile.TemporaryDirectory() as folder:
            configure_logging(folder, "application.log")
            logging.getLogger("app").info("request accepted")
            logging.getLogger("app.jobs").warning("scheduled run delayed")
            logging.getLogger("app.frontend").error("browser validation failed")
            path = Path(folder) / "application.log"
            self.assertTrue(path.is_file())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 6)
            self.assertIn("| INFO     | app | request accepted", lines[0])
            self.assertEqual(lines[1], "")
            self.assertIn("| WARNING  | app.jobs | scheduled run delayed", lines[2])
            self.assertEqual(lines[3], "")
            self.assertIn("| ERROR    | app.frontend | browser validation failed", lines[4])
            self.assertEqual(lines[5], "")
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["application.log"])

    def test_log_file_must_stay_inside_log_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                configure_logging(folder, "../outside.log")

    def test_exception_traceback_lines_are_grouped_under_the_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            configure_logging(folder, "application.log")
            try:
                raise ValueError("formatted failure")
            except ValueError:
                logging.getLogger("app.jobs").exception("job failed")
            lines = (Path(folder) / "application.log").read_text(encoding="utf-8").splitlines()
            self.assertIn("| ERROR    | app.jobs | job failed", lines[0])
            self.assertTrue(all(line.startswith("    | ") for line in lines[1:-1]))
            self.assertEqual(lines[-1], "")
