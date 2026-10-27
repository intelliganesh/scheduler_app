from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from app.services.scheduler_service import MonthlyLastDayTrigger


IST = ZoneInfo("Asia/Kolkata")


class MonthlyLastDayTriggerTests(unittest.TestCase):
    def test_day_31_clamps_short_months(self):
        trigger = MonthlyLastDayTrigger(31, 9, 0, datetime(2026, 1, 1), IST)
        first = trigger.get_next_fire_time(None, datetime(2026, 1, 1, tzinfo=IST))
        second = trigger.get_next_fire_time(first, first)
        third = trigger.get_next_fire_time(second, second)
        self.assertEqual(first.date().isoformat(), "2026-01-31")
        self.assertEqual(second.date().isoformat(), "2026-02-28")
        self.assertEqual(third.date().isoformat(), "2026-03-31")

    def test_day_29_uses_leap_day_when_available(self):
        trigger = MonthlyLastDayTrigger(29, 9, 0, datetime(2028, 1, 1), IST)
        january = trigger.get_next_fire_time(None, datetime(2028, 1, 1, tzinfo=IST))
        february = trigger.get_next_fire_time(january, january)
        self.assertEqual(january.date().isoformat(), "2028-01-29")
        self.assertEqual(february.date().isoformat(), "2028-02-29")


if __name__ == "__main__":
    unittest.main()
