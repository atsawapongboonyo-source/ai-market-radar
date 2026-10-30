import unittest
from market_data_freshness_v1 import classify_freshness as check


class MarketDataFreshnessTests(unittest.TestCase):
    NOW = "2026-10-30T13:00:00Z"

    def test_fresh_boundary(self):
        self.assertEqual(check("2026-10-30T12:57:00Z", self.NOW)["freshness"], "FRESH")

    def test_stale_after_boundary(self):
        self.assertEqual(check("2026-10-30T12:56:59Z", self.NOW)["freshness"], "STALE")

    def test_cache_does_not_make_stale_bar_fresh(self):
        result = check("2026-10-30T12:00:00Z", self.NOW, cached=True)
        self.assertEqual(result["freshness"], "STALE")
        self.assertTrue(result["cached"])

    def test_timezone_offsets(self):
        self.assertEqual(check("2026-10-30T19:59:00+07:00", self.NOW)["age_seconds"], 60)

    def test_future_bar_unknown(self):
        self.assertEqual(check("2026-10-30T13:00:01Z", self.NOW)["freshness"], "UNKNOWN")

    def test_missing_and_naive_unknown(self):
        for value in (None, "", "not a date", "2026-10-30T12:59:00"):
            with self.subTest(value=value):
                self.assertEqual(check(value, self.NOW)["freshness"], "UNKNOWN")

    def test_invalid_threshold_unknown(self):
        for threshold in (-1, None, float("nan"), True):
            with self.subTest(threshold=threshold):
                self.assertEqual(check(self.NOW, self.NOW, max_age_seconds=threshold)["freshness"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
