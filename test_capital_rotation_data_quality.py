import unittest
from datetime import datetime, timezone, timedelta
from capital_rotation_data_quality import validate_snapshot
from capital_rotation_offline import SECTORS
from capital_rotation_confirmation import confirm_rotation


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 0, tzinfo=timezone.utc)
        stamp = (self.now - timedelta(hours=2)).isoformat()
        self.snapshot = {}
        for window in ("5d", "20d"):
            self.snapshot[window] = {
                symbol: {"return_pct": value, "asof_utc": stamp}
                for symbol, value in {"SPY": -1, "SMH": -3, "SOXX": -4, **{s: 1 for s in SECTORS}}.items()
            }

    def test_valid_snapshot_feeds_classifier(self):
        checked = validate_snapshot(self.snapshot, now_utc=self.now)
        self.assertTrue(checked["ok"])
        result = confirm_rotation(checked["windows"], checked["freshness"])
        self.assertEqual(result["regime"], "CONFIRMED_RELATIVE_ROTATION")
        self.assertFalse(result["trade_signal"])

    def test_required_stale(self):
        self.snapshot["20d"]["SMH"]["asof_utc"] = (self.now - timedelta(hours=72)).isoformat()
        self.assertEqual(validate_snapshot(self.snapshot, now_utc=self.now)["reason"], "MISSING_OR_STALE_REQUIRED")

    def test_future_timestamp_rejected(self):
        self.snapshot["5d"]["SPY"]["asof_utc"] = (self.now + timedelta(hours=1)).isoformat()
        self.assertFalse(validate_snapshot(self.snapshot, now_utc=self.now)["ok"])

    def test_sector_timestamp_skew_fails_closed(self):
        for sector in SECTORS:
            self.snapshot["5d"][sector]["asof_utc"] = (self.now - timedelta(hours=20)).isoformat()
        self.assertEqual(validate_snapshot(self.snapshot, now_utc=self.now)["reason"], "SKEWED_SECTORS")

    def test_invalid_number_excluded(self):
        self.snapshot["5d"]["XLV"]["return_pct"] = float("nan")
        checked = validate_snapshot(self.snapshot, now_utc=self.now)
        self.assertTrue(checked["ok"])
        self.assertNotIn("XLV", checked["freshness"]["5d"])

    def test_missing_window(self):
        del self.snapshot["20d"]
        self.assertEqual(validate_snapshot(self.snapshot, now_utc=self.now)["reason"], "MISSING_WINDOW")


if __name__ == "__main__":
    unittest.main()
