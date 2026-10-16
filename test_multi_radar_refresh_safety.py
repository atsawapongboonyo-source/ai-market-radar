"""Safety regression tests for Multi-Radar refresh coordination (no ranking changes)."""
import unittest
from unittest.mock import patch
import multi_radar as radar


class MultiRadarRefreshSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_backoff = radar._FAILURE_UNTIL
        radar._FAILURE_UNTIL = 0.0
        self.original_cache = dict(radar._CACHE)
        radar._CACHE.update(ts=0.0, payload=None)

    def tearDown(self):
        radar._CACHE.update(self.original_cache)
        radar._FAILURE_UNTIL = self.original_backoff

    def test_concurrent_refresh_returns_cached_data_without_downloading(self):
        radar._CACHE.update(ts=0.0, payload={"version": "5.1", "leader": None})
        radar._REFRESH_LOCK.acquire()
        try:
            with patch.object(radar, "_download") as download:
                result = radar.build_multi_radar(force=True)
                download.assert_not_called()
            self.assertTrue(result["cached"])
            self.assertTrue(result["refresh_in_progress"])
        finally:
            radar._REFRESH_LOCK.release()

    def test_concurrent_refresh_without_cache_fails_closed(self):
        radar._REFRESH_LOCK.acquire()
        try:
            with patch.object(radar, "_download") as download:
                with self.assertRaisesRegex(RuntimeError, "refresh already in progress"):
                    radar.build_multi_radar(force=True)
                download.assert_not_called()
        finally:
            radar._REFRESH_LOCK.release()

    def test_failed_download_releases_lock_and_preserves_previous_cache(self):
        old_payload = {"version": "5.1", "leader": {"key": "prior"}}
        radar._CACHE.update(ts=0.0, payload=old_payload)
        with patch.object(radar, "_load_config", return_value={"benchmark": "SPY", "themes": {}}):
            with patch.object(radar, "_download", side_effect=TimeoutError("upstream timeout")):
                with self.assertRaisesRegex(TimeoutError, "upstream timeout"):
                    radar.build_multi_radar(force=True)
        self.assertFalse(radar._REFRESH_LOCK.locked())
        self.assertEqual(radar._CACHE["payload"], old_payload)

    def test_failure_enters_cooldown_without_second_provider_call(self):
        with patch.object(radar, "_build_multi_radar_uncached", side_effect=TimeoutError("provider")) as build:
            with self.assertRaises(TimeoutError):
                radar.build_multi_radar(force=True)
            with self.assertRaisesRegex(RuntimeError, "cooling down"):
                radar.build_multi_radar(force=True)
            self.assertEqual(build.call_count, 1)

    def test_cooldown_expiry_allows_retry(self):
        radar._FAILURE_UNTIL = radar.time.time() - 1
        with patch.object(radar, "_build_multi_radar_uncached", return_value={"version": "5.1"}) as build:
            self.assertEqual(radar.build_multi_radar(force=True)["version"], "5.1")
            build.assert_called_once()

    def test_fresh_cache_does_not_trigger_download(self):
        radar._CACHE.update(ts=radar.time.time(), payload={"version": "5.1"})
        with patch.object(radar, "_download") as download:
            result = radar.build_multi_radar()
            download.assert_not_called()
        self.assertTrue(result["cached"])


if __name__ == "__main__":
    unittest.main()
