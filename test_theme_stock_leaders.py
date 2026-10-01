import unittest

from theme_stock_leaders import _rank_stocks


class ThemeStockLeaderTests(unittest.TestCase):
    def _row(self, ticker, r1, r5, r20, vol, ema=True):
        return {
            "ticker": ticker,
            "price": 100.0,
            "return_1d_pct": r1,
            "return_5d_pct": r5,
            "return_20d_pct": r20,
            "relative_proxy_1d_pct": r1,
            "relative_proxy_5d_pct": r5,
            "relative_proxy_20d_pct": r20,
            "relative_qqq_5d_pct": r5,
            "above_ema20": ema,
            "volume_ratio": vol,
        }

    def test_strong_relative_stock_ranks_first(self):
        rows = [
            self._row("AAA", 2.0, 5.0, 9.0, 1.5, True),
            self._row("BBB", 0.5, 1.0, 2.0, 1.0, True),
            self._row("CCC", -1.0, -3.0, -4.0, 0.7, False),
        ]
        ranked = _rank_stocks(rows)
        self.assertEqual(ranked[0]["ticker"], "AAA")
        self.assertEqual(ranked[0]["state"], "GROUP_LEADER")
        self.assertEqual(ranked[0]["confirmation_count"], 5)

    def test_weak_stock_is_not_group_leader(self):
        rows = [
            self._row("AAA", 1.0, 2.0, 3.0, 1.2, True),
            self._row("BBB", -1.0, -2.0, -3.0, 0.6, False),
            self._row("CCC", 0.0, -1.0, -2.0, 0.8, False),
        ]
        ranked = _rank_stocks(rows)
        weak = next(x for x in ranked if x["ticker"] == "BBB")
        self.assertNotEqual(weak["state"], "GROUP_LEADER")
        self.assertLess(weak["confirmation_count"], 3)

    def test_qualified_leader_beats_higher_raw_low_confirmation(self):
        rows = [
            self._row("FAST", 10.0, 15.0, 20.0, 0.5, False),
            self._row("SOLID", 2.0, 4.0, 6.0, 1.2, True),
            self._row("WEAK", -1.0, -2.0, -3.0, 0.7, False),
        ]
        ranked = _rank_stocks(rows)
        self.assertEqual(ranked[0]["ticker"], "SOLID")
        self.assertEqual(ranked[0]["state"], "GROUP_LEADER")
        fast = next(x for x in ranked if x["ticker"] == "FAST")
        self.assertEqual(fast["confirmation_count"], 3)

    def test_scores_stay_bounded(self):
        rows = [
            self._row("AAA", 100.0, 200.0, 300.0, 10.0, True),
            self._row("BBB", -100.0, -200.0, -300.0, 0.1, False),
            self._row("CCC", 0.0, 0.0, 0.0, 1.0, True),
        ]
        ranked = _rank_stocks(rows)
        self.assertTrue(all(0 <= x["leader_score"] <= 100 for x in ranked))


if __name__ == "__main__":
    unittest.main()
