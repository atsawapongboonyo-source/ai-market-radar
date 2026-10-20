import unittest
from datetime import date, datetime, timezone
from capital_rotation_calendar import (CalendarError, is_session, session_close,
                                      last_completed_session, trailing_sessions,
                                      calendar_age_limit)


class CalendarTests(unittest.TestCase):
    def test_mid_session_uses_previous_close(self):
        self.assertEqual(last_completed_session(datetime(2026, 10, 20, 18, tzinfo=timezone.utc)), date(2026, 10, 19))

    def test_close_requires_publication_buffer(self):
        self.assertEqual(last_completed_session(datetime(2026, 10, 20, 20, 19, tzinfo=timezone.utc)), date(2026, 10, 19))
        self.assertEqual(last_completed_session(datetime(2026, 10, 20, 20, 20, tzinfo=timezone.utc)), date(2026, 10, 20))

    def test_holiday_weekend_and_age(self):
        now = datetime(2026, 7, 6, 12, tzinfo=timezone.utc)
        self.assertEqual(last_completed_session(now), date(2026, 7, 2))
        self.assertGreater(calendar_age_limit(date(2026, 7, 2), now), 80)
        with self.assertRaises(CalendarError):
            calendar_age_limit(date(2026, 7, 1), now)

    def test_early_close_and_standard_time(self):
        self.assertEqual(session_close(date(2026, 11, 27)).hour, 18)
        self.assertEqual(last_completed_session(datetime(2026, 11, 27, 18, 20, tzinfo=timezone.utc)), date(2026, 11, 27))
        self.assertEqual(session_close(date(2026, 11, 2)).hour, 21)
        self.assertEqual(session_close(date(2026, 10, 30)).hour, 20)

    def test_calendar_not_bank_holidays(self):
        self.assertTrue(is_session(date(2026, 10, 12)))
        self.assertTrue(is_session(date(2027, 12, 31)))
        self.assertFalse(is_session(date(2026, 4, 3)))

    def test_unknown_year_and_naive_time_fail_closed(self):
        for call in (lambda: is_session(date(2029, 1, 2)),
                     lambda: last_completed_session(datetime(2026, 10, 20)),
                     lambda: trailing_sessions(date(2026, 1, 2))):
            with self.assertRaises(CalendarError):
                call()

    def test_twenty_one_sessions_skip_exchange_holiday(self):
        days = trailing_sessions(date(2026, 7, 6))
        self.assertEqual(len(days), 21)
        self.assertNotIn(date(2026, 7, 3), days)
        self.assertNotIn(date(2026, 6, 19), days)
