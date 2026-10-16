import unittest
from capital_rotation_confirmation import confirm_rotation
from capital_rotation_offline import SECTORS


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.windows = {
            "5d": {"SPY": -1, "SMH": -4, "SOXX": -3},
            "20d": {"SPY": -2, "SMH": -7, "SOXX": -6},
        }
        for window in self.windows:
            self.windows[window].update({symbol: -3 for symbol in SECTORS})
        self.windows["5d"]["XLV"] = 2
        self.windows["20d"]["XLV"] = 4
        self.freshness = {window: set(data) for window, data in self.windows.items()}

    def test_two_window_rotation(self):
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "CONFIRMED_RELATIVE_ROTATION")
        self.assertEqual([x["symbol"] for x in result["candidates"]], ["XLV"])
        self.assertFalse(result["trade_signal"])

    def test_one_window_bounce_not_confirmed(self):
        self.windows["20d"]["XLV"] = -4
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "BROAD_RISK_OFF")
        self.assertEqual(result["candidates"], [])

    def test_ai_leadership_prevents_outflow_claim(self):
        self.windows["5d"]["SMH"] = 5
        self.windows["5d"]["SOXX"] = 4
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "AI_LEADING_OR_MIXED")
        self.assertEqual(result["candidates"], [])

    def test_stale_twenty_day_ai_data_fails_closed(self):
        self.freshness["20d"].remove("SMH")
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "INSUFFICIENT_DATA")

    def test_invalid_sector_return_excluded(self):
        self.windows["5d"]["XLV"] = float("inf")
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "BROAD_RISK_OFF")

    def test_sector_coverage_guard(self):
        self.freshness["20d"] = {"SPY", "SMH", "SOXX", "XLV"}
        result = confirm_rotation(self.windows, self.freshness)
        self.assertEqual(result["regime"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
