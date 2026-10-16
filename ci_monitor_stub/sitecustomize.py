"""CI-only startup shim: prevent monitor's market loop from running.

Loaded by Python through PYTHONPATH before Gunicorn imports scanner.
Never use in production. Real monitor thread starts, but its target is replaced
with a harmless no-op. Other threads retain their normal behavior.
"""
import threading

_original_start = threading.Thread.start

def _offline_safe_start(self, *args, **kwargs):
    if self.name == "ai-radar-server-monitor":
        self._target = lambda: None
        self._args = ()
        self._kwargs = {}
    return _original_start(self, *args, **kwargs)

threading.Thread.start = _offline_safe_start
