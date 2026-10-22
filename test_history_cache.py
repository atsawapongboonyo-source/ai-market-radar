"""Retention limits and real download-path copy semantics, entirely offline."""
import unittest
from unittest.mock import patch
import pandas as pd
from history_cache import HistoryCache


class HistoryCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.frame = pd.DataFrame({'Close': [1., 2., 3.]})
        self.size = int(self.frame.memory_usage(index=True, deep=True).sum())

    def cache(self, **kwargs):
        return HistoryCache(clock=lambda: self.now, **kwargs)

    def test_expired_unrelated_entries_are_released(self):
        cache = self.cache(ttl=10)
        cache['old'] = (self.now, self.frame)
        self.now += 10
        cache['new'] = (self.now, self.frame)
        self.assertEqual(len(cache), 1)
        self.assertIsNone(cache.get('old'))

    def test_bytes_lru_and_oversized_response(self):
        cache = self.cache(max_bytes=self.size * 2, max_entries=10)
        for key in ('a', 'b'):
            cache[key] = (self.now, self.frame)
        cache.get('a')
        cache['c'] = (self.now, self.frame)
        self.assertIsNone(cache.get('b'))
        self.assertEqual(len(cache), 2)
        cache['a'] = (self.now, pd.DataFrame({'Close': range(1000)}))
        self.assertIsNone(cache.get('a'))
        self.assertEqual(len(cache), 1)

    def test_entry_limit_and_backward_clock(self):
        cache = self.cache(max_entries=1)
        cache['a'] = (self.now, self.frame)
        cache['b'] = (self.now, self.frame)
        self.assertIsNone(cache.get('a'))
        self.now -= 1
        self.assertEqual(len(cache), 0)

    def test_download_values_and_independent_cache_hit_copy(self):
        import app as core
        cache = self.cache()
        with patch.object(core, '_HISTORY_CACHE', cache), patch.object(core.time, 'time', return_value=self.now), \
             patch.object(core.yf, 'download', return_value=self.frame.copy()) as download:
            fresh = core.download_history('TEST')
            fresh.iloc[0, 0] = 99
            hit = core.download_history('TEST')
            pd.testing.assert_frame_equal(hit, self.frame)
            hit.iloc[0, 0] = 88
            pd.testing.assert_frame_equal(core.download_history('TEST'), self.frame)
            self.assertEqual(download.call_count, 1)

    def test_concurrent_insertion_stays_within_budget(self):
        from concurrent.futures import ThreadPoolExecutor
        cache = self.cache(max_bytes=self.size * 3, max_entries=2)
        def write(i):
            cache[str(i)] = (self.now, self.frame.copy())
            cache.get(str(i))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(50)))
        self.assertLessEqual(len(cache), 2)
        self.assertEqual(cache._bytes, len(cache) * self.size)
