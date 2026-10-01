import unittest

from multi_radar import _rotation_confirmation, _rotation_summary, _state


class MultiRadarLogicTests(unittest.TestCase):
    def test_confirmed_early_rotation(self):
        row = {
            "rank": 2,
            "score": 0.0,
            "breadth_5d_pct": 66.7,
            "above_ema20_pct": 66.7,
            "member_median_rel_20d_pct": 2.63,
            "proxy_rel_5d_pct": 0.02,
            "volume_ratio_median": 0.85,
        }
        metrics = {"score_change_1d": 1.0, "score_change_5d": 22.8, "rank_change_5d": 2}
        row.update(_rotation_confirmation(row))
        self.assertTrue(row["rotation_confirmed"])
        self.assertEqual(row["rotation_confirmation_count"], 4)
        self.assertEqual(_state(row, metrics)[0], "EARLY_ROTATION")
    def test_weak_rebound_is_recovering(self):
        row = {
            "rank": 6,
            "score": -68.1,
            "breadth_5d_pct": 0.0,
            "above_ema20_pct": 0.0,
            "member_median_rel_20d_pct": -13.93,
            "proxy_rel_5d_pct": -3.2,
            "volume_ratio_median": 1.17,
        }
        metrics = {"score_change_1d": 2.0, "score_change_5d": 11.1, "rank_change_5d": 1}
        row.update(_rotation_confirmation(row))
        self.assertFalse(row["rotation_confirmed"])
        self.assertEqual(row["rotation_confirmation_count"], 1)
        self.assertEqual(_state(row, metrics)[0], "RECOVERING")

    def test_leader_can_be_cooling(self):
        row = {
            "rank": 1,
            "score": 17.1,
            "breadth_5d_pct": 50.0,
            "above_ema20_pct": 100.0,
            "member_median_rel_20d_pct": 8.95,
            "proxy_rel_5d_pct": -0.69,
            "volume_ratio_median": 0.80,
        }
        metrics = {"score_change_1d": 2.0, "score_change_5d": -18.4, "rank_change_5d": 0}
        row.update(_rotation_confirmation(row))
        self.assertEqual(_state(row, metrics)[0], "COOLING")

    def test_rotation_summary_tracks_handoff_and_streak(self):
        history = [
            {"date": "2026-09-28", "leader": "ai", "leader_label": "AI", "leader_score": 20},
            {"date": "2026-09-29", "leader": "ai", "leader_label": "AI", "leader_score": 18},
            {"date": "2026-09-30", "leader": "robotics", "leader_label": "Robotics", "leader_score": 14},
            {"date": "2026-10-01", "leader": "robotics", "leader_label": "Robotics", "leader_score": 17},
        ]
        result = _rotation_summary(history)
        self.assertEqual(result["leader_changes"], 1)
        self.assertEqual(result["leader_streak_sessions"], 2)
        self.assertEqual(result["last_handoff"]["from"], "ai")
        self.assertEqual(result["last_handoff"]["to"], "robotics")


if __name__ == "__main__":
    unittest.main()
