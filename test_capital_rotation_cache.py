import unittest
from capital_rotation_cache import SnapshotCache


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.cache = SnapshotCache(ttl_seconds=10, clock=lambda: self.now[0])

    def test_cache_hit_avoids_repeat_fetch(self):
        calls = []
        def fetch():
            calls.append(1)
            return {"snapshot": 1}
        self.assertEqual(self.cache.refresh(fetch)[0], "REFRESHED")
        self.assertEqual(self.cache.refresh(fetch)[0], "HIT")
        self.assertEqual(len(calls), 1)

    def test_expired_cache_not_served(self):
        self.cache.refresh(lambda: {"snapshot": 1})
        self.now[0] += 11
        self.assertIsNone(self.cache.read())

    def test_refresh_error_fails_closed(self):
        self.cache.refresh(lambda: {"snapshot": 1})
        self.now[0] += 11
        def broken():
            raise RuntimeError("provider unavailable")
        self.assertEqual(self.cache.refresh(broken), ("ERROR", None))
        self.assertIsNone(self.cache.read())

    def test_invalid_fetch_not_cached(self):
        self.assertEqual(self.cache.refresh(lambda: {}), ("INVALID", None))
        self.assertIsNone(self.cache.read())

    def test_concurrent_refresh_returns_busy(self):
        def fetch():
            status, snapshot = self.cache.refresh(lambda: {"snapshot": 2})
            self.assertEqual((status, snapshot), ("BUSY", None))
            return {"snapshot": 1}
        self.assertEqual(self.cache.refresh(fetch)[0], "REFRESHED")

    def test_new_data_replaces_expired(self):
        self.cache.refresh(lambda: {"snapshot": 1})
        self.now[0] += 11
        self.assertEqual(self.cache.refresh(lambda: {"snapshot": 2}), ("REFRESHED", {"snapshot": 2}))


if __name__ == "__main__":
    unittest.main()
