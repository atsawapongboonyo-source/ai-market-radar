import unittest
from unittest.mock import patch

from focus_queue import _candidate_keys, _stock_focus, build_focus_queue
from focus_queue_research import _secondary_reorder_research


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

    def test_secondary_quality_reorder_can_select_priority_three(self):
        records = [
            {"date": "2026-10-01", "priority": 2, "theme_rank": 3, "theme_excess_pct": 0.2,
             "stock_qualified": True, "stock_score": 60, "stock_excess_pct": 1.0},
            {"date": "2026-10-01", "priority": 3, "theme_rank": 2, "theme_excess_pct": 0.5,
             "stock_qualified": True, "stock_score": 80, "stock_excess_pct": 3.0},
        ]
        result = _secondary_reorder_research(records)
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["quality_selected_p3_pct"], 100.0)
        self.assertEqual(result["quality_pick_stock"]["avg"], 3.0)
        self.assertEqual(result["actual_p2_stock"]["avg"], 1.0)

    def test_focus_queue_survives_one_stock_data_failure(self):
        radar = {
            "themes": [
                {"key": "cybersecurity", "label": "Cybersecurity", "rank": 1, "score": 10,
                 "state": "LEADING", "state_label": "Leading", "score_change_5d": 1,
                 "rank_change_5d": 0, "rotation_confirmation_count": 4, "rotation_confirmation_total": 5},
                {"key": "robotics", "label": "Robotics", "rank": 2, "score": 5,
                 "state": "EARLY_ROTATION", "state_label": "Early Rotation", "score_change_5d": 8,
                 "rank_change_5d": 1, "rotation_confirmation_count": 4, "rotation_confirmation_total": 5},
                {"key": "quantum", "label": "Quantum", "rank": 3, "score": 2,
                 "state": "NEUTRAL", "state_label": "Neutral", "score_change_5d": 0,
                 "rank_change_5d": 0, "rotation_confirmation_count": 2, "rotation_confirmation_total": 5},
            ],
            "leader": {"key": "cybersecurity"},
            "rotation_summary": {},
        }

        def fake_stocks(key, force=False):
            if key == "robotics":
                raise RuntimeError("temporary data failure")
            return {"top3": [{
                "ticker": "AAA", "rank": 1, "leader_score": 75,
                "confirmation_count": 4, "confirmation_total": 5,
                "state": "GROUP_LEADER", "state_label": "Group Leader",
                "relative_proxy_5d_pct": 2.0, "relative_proxy_20d_pct": 4.0,
                "volume_ratio": 1.2, "above_ema20": True,
            }]}

        with patch("focus_queue.build_multi_radar", return_value=radar), patch(
            "focus_queue.build_theme_stock_leaders", side_effect=fake_stocks
        ):
            result = build_focus_queue(force=True)

        self.assertEqual(len(result["queue"]), 3)
        failed = next(x for x in result["queue"] if x["key"] == "robotics")
        self.assertIsNone(failed["stock"])
        self.assertEqual(failed["stock_note"], "Stock Leader data unavailable")
        self.assertIn("temporary data failure", failed["stock_error"])

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
