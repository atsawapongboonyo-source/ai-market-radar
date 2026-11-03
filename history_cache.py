"""Bound retained history frames without changing downloads or indicator values."""
from collections import OrderedDict
from threading import RLock
import time


class HistoryCache:
    def __init__(self, *, max_bytes=8 * 2**20, max_entries=128, ttl=900, clock=None):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.ttl = ttl
        self._clock = clock or (lambda: time.time())
        self._items = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def _remove(self, key):
        _, size = self._items.pop(key)
        self._bytes -= size

    def _prune(self):
        now = self._clock()
        for key, (value, _) in list(self._items.items()):
            if now - value[0] >= self.ttl or now < value[0]:
                self._remove(key)

    def get(self, key, default=None):
        with self._lock:
            self._prune()
            item = self._items.get(key)
            if item is None:
                return default
            self._items.move_to_end(key)
            return item[0]

    def __setitem__(self, key, value):
        size = int(value[1].memory_usage(index=True, deep=True).sum())
        with self._lock:
            self._prune()
            if key in self._items:
                self._remove(key)
            # An oversized response still reaches its caller, but is not retained.
            if size > self.max_bytes or self.max_entries < 1:
                return
            self._items[key] = (value, size)
            self._bytes += size
            while self._bytes > self.max_bytes or len(self._items) > self.max_entries:
                self._remove(next(iter(self._items)))

    def __len__(self):
        with self._lock:
            self._prune()
            return len(self._items)

    def values(self):
        with self._lock:
            self._prune()
            return [value for value, _ in self._items.values()]

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes = 0
