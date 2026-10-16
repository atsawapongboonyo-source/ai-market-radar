import unittest
from datetime import date, datetime, timezone
from capital_rotation_market_session import validate_completed_session


class MarketSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)  # Sunday
        self.expected = date(2026, 10, 16)  # Friday completed session
        self.snapshot = {
            w: {"SPY": {"return_pct": 1, "session_date": "2026-10-16", "asof_utc": "2026-10-16T20:00:00Z"}}
            for w in ("5d", "20d")
        }

    def test_weekend_last_completed_session_valid(self):
        self.assertTrue(validate_completed_session(self.snapshot, expected_session=self.expected, now_utc=self.now)["ok"])

    def test_holiday_gap_accepted_when_calendar_confirms(self):
        self.now = datetime(2026, 12, 26, 12, tzinfo=timezone.utc)
        self.expected = date(2026, 12, 24)
        for w in self.snapshot:
            self.snapshot[w]["SPY"]["session_date"] = "2026-12-24"
        self.assertTrue(validate_completed_session(self.snapshot, expected_session=self.expected, now_utc=self.now)["ok"])

    def test_stale_session_rejected(self):
        self.snapshot["20d"]["SPY"]["session_date"] = "2026-10-15"
        self.assertEqual(validate_completed_session(self.snapshot, expected_session=self.expected, now_utc=self.now)["reason"], "MISMATCHED_OR_STALE_SESSION")

    def test_calendar_missing_fails_closed(self):
        self.assertEqual(validate_completed_session(self.snapshot, expected_session=None, now_utc=self.now)["reason"], "MISSING_EXCHANGE_CALENDAR")

    def test_future_session_rejected(self):
        self.assertEqual(validate_completed_session(self.snapshot, expected_session=date(2026, 10, 19), now_utc=self.now)["reason"], "FUTURE_SESSION")

    def test_missing_session_date_rejected(self):
        del self.snapshot["5d"]["SPY"]["session_date"]
        self.assertEqual(validate_completed_session(self.snapshot, expected_session=self.expected, now_utc=self.now)["reason"], "MISSING_SESSION_DATE")


if __name__ == "__main__":
    unittest.main()
