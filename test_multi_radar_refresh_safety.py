"""Safety regression tests for Multi-Radar refresh coordination (no ranking changes)."""
import unittest
from unittest.mock import patch
import multi_radar as radar


class MultiRadarRefreshSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = dict(radar._CACHE)
        radar._CACHE.update(ts=0.0, payload=None)

    def tearDown(self):
        radar._CACHE.update(self.original_cache)

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

    def test_fresh_cache_does_not_trigger_download(self):
        radar._CACHE.update(ts=radar.time.time(), payload={"version": "5.1"})
        with patch.object(radar, "_download") as download:
            result = radar.build_multi_radar()
            download.assert_not_called()
        self.assertTrue(result["cached"])


if __name__ == "__main__":
    unittest.main()
