import unittest
from explosive_momentum_research import detect


def bars(last_close=12.0, last_volume=400_000):
    rows = [{"session": f"2026-10-{i:02d}", "close": 10.0, "volume": 100_000} for i in range(1, 21)]
    rows.append({"session": "2026-10-21", "close": last_close, "volume": last_volume})
    return rows


class ExplosiveMomentumResearchTests(unittest.TestCase):
    def test_early_anomaly_flag(self):
        result = detect("TEST", bars())
        self.assertEqual(result.state, "FLAGGED_FOR_REVIEW")
        self.assertEqual(result.return_pct, 20)
        self.assertEqual(result.relative_volume, 4)

    def test_does_not_chase_above_window(self):
        self.assertIn("ALREADY_ABOVE_GAIN_WINDOW", detect("TEST", bars(15)).reasons)

    def test_low_liquidity(self):
        self.assertIn("LOW_DOLLAR_LIQUIDITY", detect("TEST", bars(last_volume=10_000)).reasons)

    def test_missing_history_blocks(self):
        self.assertEqual(detect("TEST", bars()[:5]).state, "BLOCKED")

    def test_duplicate_session_blocks(self):
        rows = bars()
        rows[-1]["session"] = rows[-2]["session"]
        self.assertEqual(detect("TEST", rows).state, "BLOCKED")

    def test_invalid_data_blocks(self):
        rows = bars()
        rows[-1]["volume"] = float("nan")
        self.assertEqual(detect("TEST", rows).state, "BLOCKED")

    def test_no_flag_below_gain_window(self):
        self.assertIn("BELOW_GAIN_WINDOW", detect("TEST", bars(10.5)).reasons)


if __name__ == "__main__":
    unittest.main()
