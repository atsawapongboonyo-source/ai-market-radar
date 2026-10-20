import io
import json
import unittest
from datetime import date, timedelta
from urllib.parse import urlsplit
from capital_rotation_alpaca import (
    SYMBOLS, HOST, MarketDataError, fetch_alpaca_snapshot
)


class FakeResponse:
    def __init__(self, payload):
        self.data = io.BytesIO(json.dumps(payload).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, count):
        return self.data.read(count)


class AlpacaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.session = date(2026, 10, 16)
        # 21 consecutive weekdays ending on Friday, fixture only.
        days = []
        day = self.session
        while len(days) < 21:
            if day.weekday() < 5:
                days.append(day)
            day -= timedelta(days=1)
        self.days = list(reversed(days))
        self.payload = {"bars": {
            symbol: [{"t": d.isoformat() + "T00:00:00Z", "c": 100 + i}
                     for i, d in enumerate(self.days)]
            for symbol in SYMBOLS
        }}

    def fetch(self, payload=None, *, feed="iex"):
        def opener(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(urlsplit(request.full_url).netloc, "data.alpaca.markets")
            self.assertEqual(timeout, 12)
            self.assertEqual(request.headers["Apca-api-key-id"], "test-key")
            return FakeResponse(self.payload if payload is None else payload)
        return fetch_alpaca_snapshot(
            expected_session=self.session, api_key="test-key",
            secret_key="test-secret", feed=feed, opener=opener)

    def test_valid_bars_5_and_20_sessions(self):
        result = self.fetch()
        self.assertEqual(len(result["5d"]), len(SYMBOLS))
        self.assertAlmostEqual(result["5d"]["SPY"]["return_pct"],
                               (120 / 115 - 1) * 100)
        self.assertEqual(result["20d"]["SPY"]["session_date"], "2026-10-16")

    def test_missing_etf_fails_closed(self):
        payload = json.loads(json.dumps(self.payload))
        del payload["bars"]["XLV"]
        with self.assertRaises(MarketDataError):
            self.fetch(payload)

    def test_stale_session_fails_closed(self):
        payload = json.loads(json.dumps(self.payload))
        for symbol in SYMBOLS:
            payload["bars"][symbol].pop()
        with self.assertRaises(MarketDataError):
            self.fetch(payload)

    def test_pagination_fails_closed(self):
        with self.assertRaises(MarketDataError):
            self.fetch({"bars": self.payload["bars"], "next_page_token": "next"})

    def test_missing_credentials_fails_closed(self):
        with self.assertRaises(MarketDataError):
            fetch_alpaca_snapshot(expected_session=self.session,
                                  api_key="", secret_key="secret")

    def test_provider_errors_do_not_expose_secrets(self):
        def broken(request, timeout):
            raise RuntimeError("test-secret")
        with self.assertRaisesRegex(MarketDataError, "^PROVIDER_UNAVAILABLE$"):
            fetch_alpaca_snapshot(expected_session=self.session,
                                  api_key="test-key", secret_key="test-secret",
                                  opener=broken)

    def test_reject_unexpected_feed(self):
        with self.assertRaises(ValueError):
            self.fetch(feed="unlicensed")

    def test_different_symbol_history_fails_closed(self):
        payload = json.loads(json.dumps(self.payload))
        payload['bars']['XLV'][0]['t'] = (self.days[0] - timedelta(days=1)).isoformat() + 'T00:00:00Z'
        with self.assertRaisesRegex(MarketDataError, '^MISALIGNED_SYMBOL_SESSIONS$'):
            self.fetch(payload)

    def test_http_error_is_safely_classified(self):
        from urllib.error import HTTPError
        def denied(request, timeout):
            raise HTTPError(request.full_url, 403, 'test-secret', {}, None)
        with self.assertRaisesRegex(MarketDataError, '^FEED_ACCESS_DENIED$'):
            fetch_alpaca_snapshot(expected_session=self.session, api_key='test-key',
                                  secret_key='test-secret', opener=denied)

    def test_identical_gaps_across_all_symbols_still_fail_calendar(self):
        payload = json.loads(json.dumps(self.payload))
        for symbol in SYMBOLS:
            payload['bars'][symbol][0]['t'] = (self.days[0] - timedelta(days=1)).isoformat() + 'T00:00:00Z'
        with self.assertRaisesRegex(MarketDataError, '^MISSING_EXCHANGE_SESSIONS$'):
            self.fetch(payload)


if __name__ == "__main__":
    unittest.main()
