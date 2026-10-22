"""Opt-in, bounded, single-process cache for research-only snapshot inputs.

No background threads, network calls, broker operations, or production routes.
Cross-worker sharing is deliberately NOT provided. The fetch callback must
return a complete validated snapshot and must have its own hard deadline.
"""
import threading
import time


class SnapshotCache:
    def __init__(self, *, ttl_seconds=300, clock=None):
        if not isinstance(ttl_seconds, (int, float)) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = ttl_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._snapshot = None
        self._expires = 0

    def read(self):
        """Return a cached snapshot only while TTL remains valid."""
        with self._lock:
            if self._snapshot is not None and self._clock() < self._expires:
                return self._snapshot
            return None

    def refresh(self, fetch):
        """Nonblocking refresh. Caller supplies bounded synchronous fetch.

        Return (status, snapshot). No stale data is served. Concurrent
        requests in the same process return BUSY rather than overlapping fetch.
        """
        if not self._lock.acquire(blocking=False):
            return "BUSY", None
        try:
            now = self._clock()
            if self._snapshot is not None and now < self._expires:
                return "HIT", self._snapshot
            try:
                snapshot = fetch()
            except Exception:
                return "ERROR", None
            if not isinstance(snapshot, dict) or not snapshot:
                return "INVALID", None
            self._snapshot = snapshot
            self._expires = self._clock() + self._ttl
            return "REFRESHED", snapshot
        finally:
            self._lock.release()
