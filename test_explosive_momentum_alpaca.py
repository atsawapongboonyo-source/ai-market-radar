import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from explosive_momentum_alpaca import fetch_intraday

START = datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc)


class Response:
    def __init__(self, value):
        self.data = io.BytesIO(json.dumps(value).encode())
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.data.read(n)


class AlpacaAdapterTests(unittest.TestCase):
    def test_get_only_and_partial_feed_provenance(self):
        requests = []
        def opener(request, timeout):
            requests.append(request)
            if "/quotes/latest" in request.full_url:
                return Response({"quote": {"bp": 11.8, "ap": 11.82, "t": "2026-11-04T14:46:00Z"}})
            return Response({"bars": [{"t": "2026-11-04T14:30:00Z", "c": 11.7, "v": 10000}]})
        result = fetch_intraday("TEST", start_utc=START,
                                end_utc=START+timedelta(minutes=16),
                                api_key="test", secret_key="test", opener=opener)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(req.get_method() == "GET" for req in requests))
        self.assertEqual(result["coverage"], "PARTIAL_IEX")
        self.assertFalse(result["historical_quote_asof"])

    def test_invalid_symbol(self):
        with self.assertRaisesRegex(ValueError, "INVALID_SYMBOL"):
            fetch_intraday("../orders", start_utc=START,
                            end_utc=START+timedelta(minutes=16),
                            api_key="test", secret_key="test")


if __name__ == "__main__":
    unittest.main()
