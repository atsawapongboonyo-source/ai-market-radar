"""Offline tests for research-only universe; no market-data or trading calls."""
import copy
import unittest
from stock_radar_universe_validation import load_report, validate_universe


class StockRadarUniverseTests(unittest.TestCase):
    def test_current_universe(self):
        result = load_report()
        self.assertEqual(result["groups"], 10)
        self.assertEqual(result["research_candidates"], 40)
        self.assertEqual(result["verified_etf_funds"], 14)
        self.assertEqual(result["verified_unique_stocks"], 59)

    def test_no_unverified_ready_or_live(self):
        from json import loads
        from stock_radar_universe_validation import WATCHLIST, HOLDINGS
        w = loads(WATCHLIST.read_text(encoding="utf-8"))
        h = loads(HOLDINGS.read_text(encoding="utf-8"))
        for field, value in (("signal", "READY"), ("feed", "LIVE")):
            changed = copy.deepcopy(w)
            changed["safety"][field] = value
            with self.assertRaises(ValueError):
                validate_universe(changed, h)
        changed = copy.deepcopy(w)
        changed["groups"]["Consumer"].append(changed["groups"]["Healthcare"][0])
        with self.assertRaises(ValueError):
            validate_universe(changed, h)
        changed = copy.deepcopy(w)
        changed["safety"]["do_not_trigger_bulk_collection"] = False
        with self.assertRaises(ValueError):
            validate_universe(changed, h)


if __name__ == "__main__":
    unittest.main()
