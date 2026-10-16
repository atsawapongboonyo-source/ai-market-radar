import unittest
from capital_rotation_offline import classify_rotation, SECTORS

class CapitalRotationTests(unittest.TestCase):
    def setUp(self):
        self.prices = {"SPY": -1.0, "SMH": -4.0, "SOXX": -3.0}
        self.prices.update({s: -2.0 for s in SECTORS})
        self.fresh = set(self.prices)

    def test_ai_weak_defensives_positive(self):
        self.prices.update({"XLV": 2.0, "XLP": 1.0})
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "POSSIBLE_ROTATION")
        self.assertEqual(result["candidates"][0]["symbol"], "XLV")
        self.assertFalse(result["trade_signal"])

    def test_everything_down_is_risk_off(self):
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "BROAD_RISK_OFF")

    def test_ai_leading_is_not_outflow(self):
        self.prices.update({"SMH": 3.0, "SOXX": 2.0, "XLV": 1.0})
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "AI_LEADING_OR_MIXED")

    def test_stale_ai_proxy_fails_closed(self):
        self.fresh.remove("SOXX")
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "INSUFFICIENT_DATA")
        self.assertEqual(result["candidates"], [])

    def test_insufficient_sector_coverage_fails_closed(self):
        self.fresh = {"SPY", "SMH", "SOXX", "XLV"}
        self.prices["XLV"] = 2.0
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "INSUFFICIENT_DATA")
        self.assertEqual(result["candidates"], [])

    def test_non_finite_price_excluded(self):
        self.prices["XLV"] = float("nan")
        result = classify_rotation(self.prices, self.fresh)
        self.assertEqual(result["regime"], "BROAD_RISK_OFF")

if __name__ == "__main__":
    unittest.main()
