import unittest
from datetime import datetime, timedelta, timezone
from explosive_momentum_timing import validate_snapshot_timing

BASE = datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc)


def sample():
    bars = [{"timestamp_utc": (BASE + timedelta(minutes=i)).isoformat()}
            for i in range(16)]
    quote = {"timestamp_utc": (BASE + timedelta(minutes=16)).isoformat()}
    return {"bars": bars, "latest_quote": quote}


class TimingTests(unittest.TestCase):
    def test_fresh_contiguous(self):
        self.assertEqual(validate_snapshot_timing(sample(), BASE + timedelta(minutes=16)),
                         "READY_FOR_RESEARCH")

    def test_stale_quote(self):
        data = sample()
        data["latest_quote"]["timestamp_utc"] = BASE.isoformat()
        self.assertEqual(validate_snapshot_timing(data, BASE + timedelta(minutes=16)),
                         "STALE_QUOTE")

    def test_future_quote(self):
        data = sample()
        data["latest_quote"]["timestamp_utc"] = (BASE + timedelta(minutes=20)).isoformat()
        self.assertEqual(validate_snapshot_timing(data, BASE + timedelta(minutes=16)),
                         "STALE_QUOTE")

    def test_gap(self):
        data = sample()
        data["bars"][5]["timestamp_utc"] = (BASE + timedelta(minutes=7)).isoformat()
        self.assertEqual(validate_snapshot_timing(data, BASE + timedelta(minutes=16)),
                         "BAR_GAP")

    def test_missing_bars(self):
        data = sample()
        data["bars"] = data["bars"][:4]
        self.assertEqual(validate_snapshot_timing(data, BASE + timedelta(minutes=16)),
                         "INSUFFICIENT_BARS")


if __name__ == "__main__":
    unittest.main()
