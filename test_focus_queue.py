import unittest

from focus_queue import _candidate_keys, _stock_focus


class FocusQueueTests(unittest.TestCase):
    def test_current_leader_is_always_first(self):
        radar = {
            "themes": [
                {"key": "cybersecurity", "rank": 1, "state": "COOLING", "state_label": "Cooling", "score_change_5d": -10, "rank_change_5d": 0},
                {"key": "robotics", "rank": 2, "state": "EARLY_ROTATION", "state_label": "Early Rotation", "score_change_5d": 20, "rank_change_5d": 2},
                {"key": "quantum", "rank": 3, "state": "NEUTRAL", "state_label": "Neutral", "score_change_5d": 1, "rank_change_5d": 0},
            ]
        }
        rows = _candidate_keys(radar)
        self.assertEqual(rows[0]["key"], "cybersecurity")
        self.assertEqual(rows[0]["focus_type"], "CURRENT_LEADER")
        self.assertEqual(rows[1]["key"], "robotics")
        self.assertEqual(rows[1]["focus_type"], "ROTATION_WATCH")

    def test_queue_has_no_duplicates_and_max_three(self):
        radar = {
            "themes": [
                {"key": "ai", "rank": 1, "state": "LEADING", "state_label": "Leading", "score_change_5d": 1, "rank_change_5d": 0},
                {"key": "robotics", "rank": 2, "state": "ACCELERATING", "state_label": "Accelerating", "score_change_5d": 8, "rank_change_5d": 1},
                {"key": "quantum", "rank": 3, "state": "EARLY_ROTATION", "state_label": "Early Rotation", "score_change_5d": 9, "rank_change_5d": 1},
                {"key": "space", "rank": 4, "state": "NEUTRAL", "state_label": "Neutral", "score_change_5d": 0, "rank_change_5d": 0},
            ]
        }
        rows = _candidate_keys(radar)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({x["key"] for x in rows}), 3)
        self.assertEqual(rows[1]["key"], "robotics")

    def test_stock_focus_marks_confirmation(self):
        payload = {
            "top3": [
                {
                    "ticker": "AAA",
                    "rank": 1,
                    "leader_score": 80,
                    "confirmation_count": 4,
                    "confirmation_total": 5,
                    "state": "GROUP_LEADER",
                    "state_label": "Group Leader",
                    "relative_proxy_5d_pct": 2.0,
                    "relative_proxy_20d_pct": 5.0,
                    "volume_ratio": 1.2,
                    "above_ema20": True,
                }
            ]
        }
        result = _stock_focus(payload)
        self.assertEqual(result["ticker"], "AAA")
        self.assertTrue(result["qualified"])

    def test_stock_focus_can_be_unconfirmed(self):
        payload = {
            "top3": [
                {
                    "ticker": "BBB",
                    "rank": 1,
                    "leader_score": 70,
                    "confirmation_count": 3,
                    "confirmation_total": 5,
                    "state": "CONTENDER",
                    "state_label": "Contender",
                    "relative_proxy_5d_pct": 1.0,
                    "relative_proxy_20d_pct": 2.0,
                    "volume_ratio": 0.8,
                    "above_ema20": True,
                }
            ]
        }
        result = _stock_focus(payload)
        self.assertFalse(result["qualified"])


if __name__ == "__main__":
    unittest.main()
