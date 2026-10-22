import unittest
from datetime import datetime, date, timezone, timedelta
from capital_rotation_offline import SECTORS
from capital_rotation_pipeline import evaluate_rotation_snapshot


class RotationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 21, tzinfo=timezone.utc)
        self.session = date(2026, 10, 16)
        stamp = self.now.isoformat()
        self.snapshot = {}
        for window in ("5d", "20d"):
            self.snapshot[window] = {
                symbol: {"return_pct": value, "asof_utc": stamp, "session_date": self.session.isoformat()}
                for symbol, value in {"SPY": -1, "SMH": -4, "SOXX": -3,
                                      **{s: -2 for s in SECTORS}, "XLV": 2}.items()
            }

    def test_valid_pipeline_returns_research_not_buy(self):
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=self.session, now_utc=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["regime"], "CONFIRMED_RELATIVE_ROTATION")
        self.assertFalse(result["trade_signal"])

    def test_wrong_session_blocks(self):
        self.snapshot["20d"]["SPY"]["session_date"] = "2026-10-15"
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=self.session, now_utc=self.now)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "MISMATCHED_OR_STALE_SESSION")

    def test_stale_data_blocks(self):
        self.snapshot["5d"]["SMH"]["asof_utc"] = (self.now - timedelta(days=4)).isoformat()
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=self.session, now_utc=self.now)
        self.assertEqual(result["status"], "BLOCKED")

    def test_weekend_requires_explicit_market_gap_allowance(self):
        sunday = self.now + timedelta(days=2)
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=self.session, now_utc=sunday)
        self.assertEqual(result["status"], "BLOCKED")
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=self.session, now_utc=sunday, max_age_hours=80)
        self.assertEqual(result["status"], "RESEARCH_ONLY")

    def test_no_calendar_blocks(self):
        result = evaluate_rotation_snapshot(self.snapshot, expected_session=None, now_utc=self.now)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
