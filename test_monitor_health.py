"""Read-only monitor heartbeat diagnostics regression tests."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import server_auto_monitor as monitor


class MonitorHealthTests(unittest.TestCase):
    def setUp(self):
        self.previous = dict(monitor._STATE)
        self.previous_thread = monitor._THREAD

    def tearDown(self):
        monitor._STATE.clear()
        monitor._STATE.update(self.previous)
        monitor._THREAD = self.previous_thread

    def test_stale_heartbeat_is_not_healthy(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = True
            monitor._STATE.update(running=True, last_error=None,
                last_cycle_at=(now - timedelta(minutes=15)).isoformat(),
                session=monitor._market_window(now))
            health = monitor.status()["health"]
            self.assertEqual(health["state"], "NOT_HEALTHY")
            self.assertTrue(health["thread_alive"])
            self.assertGreater(health["last_cycle_age_seconds"], 120)

    def test_wrong_session_is_not_healthy(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = True
            monitor._STATE.update(running=True, last_error=None,
                last_cycle_at=now.isoformat(), session="INCORRECT_SESSION")
            health = monitor.status()["health"]
            self.assertEqual(health["state"], "NOT_HEALTHY")
            self.assertFalse(health["session_matches"])

    def test_fresh_heartbeat_with_matching_session(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = True
            monitor._STATE.update(running=True, last_error=None,
                last_cycle_at=now.isoformat(), session=monitor._market_window(now))
            self.assertEqual(monitor.status()["health"]["state"], "HEALTHY")

    def test_in_progress_cycle_diagnostics_visible_without_declaring_healthy(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = True
            monitor._STATE.update(
                running=True, last_error=None,
                last_cycle_at=(now - timedelta(minutes=15)).isoformat(),
                last_cycle_started_at=now.isoformat(),
                last_cycle_finished_at=None,
                last_cycle_duration_seconds=None,
                cycle_in_progress=True,
                session=monitor._market_window(now),
            )
            health = monitor.status()["health"]
            self.assertEqual(health["state"], "NOT_HEALTHY")
            self.assertTrue(health["cycle_in_progress"])
            self.assertIsNone(health["last_cycle_duration_seconds"])

    def test_completed_cycle_diagnostics_are_reported(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = True
            monitor._STATE.update(
                running=True, last_error=None, last_cycle_at=now.isoformat(),
                last_cycle_started_at=(now - timedelta(seconds=3)).isoformat(),
                last_cycle_finished_at=now.isoformat(),
                last_cycle_duration_seconds=3.0,
                cycle_in_progress=False,
                session=monitor._market_window(now),
            )
            health = monitor.status()["health"]
            self.assertEqual(health["state"], "HEALTHY")
            self.assertFalse(health["cycle_in_progress"])
            self.assertEqual(health["last_cycle_duration_seconds"], 3.0)

    def test_dead_thread_is_not_healthy(self):
        now = datetime.now(monitor.ET)
        with patch.object(monitor, "_ENABLED", True), patch.object(monitor, "_THREAD") as thread:
            thread.is_alive.return_value = False
            monitor._STATE.update(running=True, last_error=None,
                last_cycle_at=now.isoformat(), session=monitor._market_window(now))
            self.assertEqual(monitor.status()["health"]["state"], "NOT_HEALTHY")


if __name__ == "__main__":
    unittest.main()
