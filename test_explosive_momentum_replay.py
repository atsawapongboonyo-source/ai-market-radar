import unittest
from datetime import datetime, timedelta, timezone
from explosive_momentum_replay import replay_snapshots

BASE = datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc)


def snapshot(symbol="AAA", *, volume=25000, feed="SIP"):
    bars = [{"timestamp_utc": (BASE+timedelta(minutes=i)).isoformat(),
             "close": 10+0.12*i, "volume": volume} for i in range(16)]
    return {"symbol": symbol, "bars": bars, "baseline": [100000]*12,
            "observed_at_utc": BASE+timedelta(minutes=16),
            "session_open_price": 10, "bid": 11.77, "ask": 11.81,
            "feed": feed, "session": "REGULAR"}


class ReplayTests(unittest.TestCase):
    def test_counts_and_first_review(self):
        result = replay_snapshots([snapshot("AAA"),snapshot("BBB",feed="IEX"),
                                   snapshot("CCC",volume=10)])
        self.assertEqual(result["snapshots"],3)
        self.assertEqual(result["states"]["REVIEW"],1)
        self.assertEqual(result["states"]["WATCH"],2)
        self.assertEqual(set(result["first_review_utc"]),{"AAA"})
        self.assertIn("NO_PRECISION_CLAIM",result["limitations"])

    def test_input_order_does_not_change_results(self):
        rows = [snapshot("BBB",feed="IEX"),snapshot("AAA")]
        self.assertEqual(replay_snapshots(rows),replay_snapshots(list(reversed(rows))))

    def test_observation_time_required(self):
        row = snapshot()
        row["observed_at_utc"] = None
        with self.assertRaisesRegex(ValueError,"OBSERVATION_TIME_REQUIRED"):
            replay_snapshots([row])

    def test_empty_input(self):
        result = replay_snapshots([])
        self.assertEqual(result["snapshots"],0)
        self.assertEqual(result["first_review_utc"],{})


if __name__ == "__main__":
    unittest.main()
