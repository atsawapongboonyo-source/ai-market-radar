import unittest
from datetime import datetime, timedelta, timezone
from explosive_momentum_intraday import detect_intraday

BASE = datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc)


def fixture(**changes):
    bars = []
    for i in range(16):
        bars.append({"timestamp_utc": (BASE + timedelta(minutes=i)).isoformat(),
                     "close": 10 + 0.12*i, "volume": 25000})
    args = dict(symbol="TEST", bars=bars,
                baseline_same_clock_volumes=[100000]*12,
                observed_at_utc=BASE + timedelta(minutes=16),
                session_open_price=10, bid=11.77, ask=11.81,
                feed="SIP", session="REGULAR")
    args.update(changes)
    return args


class IntradayMomentumTests(unittest.TestCase):
    def test_research_review(self):
        result = detect_intraday(**fixture())
        self.assertEqual(result.state, "REVIEW")
        self.assertEqual(result.gain_pct, 18)
        self.assertEqual(result.relative_volume, 3.75)

    def test_partial_iex_feed_not_full_market_confirmation(self):
        result = detect_intraday(**fixture(feed="IEX"))
        self.assertEqual(result.state, "WATCH")
        self.assertIn("PARTIAL_MARKET_FEED", result.reasons)

    def test_stale_blocks(self):
        result = detect_intraday(**fixture(observed_at_utc=BASE+timedelta(minutes=25)))
        self.assertEqual(result.state, "BLOCKED")

    def test_missing_baseline_blocks(self):
        result = detect_intraday(**fixture(baseline_same_clock_volumes=[100000]*3))
        self.assertEqual(result.state, "BLOCKED")

    def test_noncontiguous_blocks(self):
        args = fixture()
        args["bars"][8]["timestamp_utc"] = (BASE+timedelta(minutes=20)).isoformat()
        self.assertEqual(detect_intraday(**args).state, "BLOCKED")

    def test_wide_spread(self):
        result = detect_intraday(**fixture(bid=11,ask=12))
        self.assertIn("WIDE_SPREAD",result.reasons)

    def test_overextended(self):
        result = detect_intraday(**fixture(session_open_price=8))
        self.assertEqual(result.state,"OVEREXTENDED")

    def test_no_future_bar(self):
        self.assertEqual(detect_intraday(**fixture(observed_at_utc=BASE)).state,"BLOCKED")

    def test_invalid_quotes(self):
        self.assertEqual(detect_intraday(**fixture(bid=12,ask=11)).state,"BLOCKED")

    def test_weak_volume(self):
        args = fixture()
        for b in args["bars"]: b["volume"] = 100
        result = detect_intraday(**args)
        self.assertIn("LOW_RELATIVE_VOLUME",result.reasons)
        self.assertIn("LOW_TURNOVER",result.reasons)


if __name__ == "__main__":
    unittest.main()
