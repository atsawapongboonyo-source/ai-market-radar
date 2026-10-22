import unittest
from datetime import date, datetime, timezone
from capital_rotation_offline import SECTORS
from capital_rotation_report import build_report


class LocalReportTests(unittest.TestCase):
    def test_complete_snapshot_returns_read_only_report(self):
        now = datetime(2026, 10, 16, 21, tzinfo=timezone.utc)
        stamp = "2026-10-16T20:00:00Z"
        snapshot = {}
        for window in ("5d", "20d"):
            values = {"SPY": -1, "SMH": -4, "SOXX": -3}
            values.update({symbol: -2 for symbol in SECTORS})
            values["XLV"] = 3
            snapshot[window] = {
                symbol: {"return_pct": value, "asof_utc": stamp,
                         "session_date": "2026-10-16"}
                for symbol, value in values.items()
            }
        report = build_report(snapshot, expected_session=date(2026, 10, 16),
                              now_utc=now)
        self.assertEqual(report["result"]["status"], "RESEARCH_ONLY")
        self.assertFalse(report["result"]["trade_signal"])
        self.assertIn("NOT measured fund flows", report["disclaimer"])

    def test_missing_snapshot_is_blocked(self):
        report = build_report({}, expected_session=date(2026, 10, 16),
                              now_utc=datetime(2026, 10, 16, 21, tzinfo=timezone.utc))
        self.assertEqual(report["result"]["status"], "BLOCKED")
        self.assertEqual(report["result"]["candidates"], [])
        self.assertFalse(report["result"]["trade_signal"])


if __name__ == "__main__":
    unittest.main()
