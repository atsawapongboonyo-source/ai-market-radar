import unittest
from datetime import datetime, timezone, timedelta
from webull_quote_autofill import normalize_quote


class QuoteValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 14, tzinfo=timezone.utc)
        self.quote = {"symbol": "GOOGL", "price": "350.33",
                      "pre_close": "347.64",
                      "last_trade_time": int(self.now.timestamp() * 1000)}

    def test_valid_quote_remains_unverified(self):
        result = normalize_quote(self.quote, "GOOGL", self.now)
        self.assertEqual(result["price"], "350.33")
        self.assertFalse(result["autofill_eligible"])

    def test_symbol_mismatch(self):
        with self.assertRaises(ValueError):
            normalize_quote(self.quote, "NVDA", self.now)

    def test_stale_quote(self):
        with self.assertRaises(ValueError):
            normalize_quote(self.quote, "GOOGL", self.now + timedelta(minutes=5))

    def test_future_quote(self):
        with self.assertRaises(ValueError):
            normalize_quote(self.quote, "GOOGL", self.now - timedelta(seconds=1))

    def test_invalid_price(self):
        self.quote["price"] = "NaN"
        with self.assertRaises(ValueError):
            normalize_quote(self.quote, "GOOGL", self.now)

    def test_missing_timestamp(self):
        del self.quote["last_trade_time"]
        with self.assertRaises(ValueError):
            normalize_quote(self.quote, "GOOGL", self.now)


if __name__ == "__main__":
    unittest.main()
