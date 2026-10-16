"""Exercise monitor thread startup with a harmless replacement loop.

No network, market data, alerts, or broker actions. Unlike the import-wiring
test, this test starts a real thread, but replaces the monitor loop before
calling the original start function.
"""
import os
import threading

for key, value in (
    ("SERVER_AUTO_MONITOR_ENABLED", "1"),
    ("TELEGRAM_TEST_ON_BOOT", "0"),
    ("LIVE_TRADING", "0"),
):
    assert os.environ.get(key) == value, key

original_start = threading.Thread.start
intercepted = []

def block_import_start(self, *args, **kwargs):
    if self.name != "ai-radar-server-monitor":
        raise AssertionError("unexpected startup: " + self.name)
    intercepted.append(self)
    return None

threading.Thread.start = block_import_start
try:
    import scanner
finally:
    threading.Thread.start = original_start

import server_auto_monitor as monitor
assert len(intercepted) == 1
assert not intercepted[0].is_alive()

ran = threading.Event()
def harmless_loop():
    ran.set()

monitor._loop = harmless_loop
assert monitor.start_server_monitor() is True
thread = monitor._THREAD
thread.join(timeout=3)
assert ran.is_set(), "harmless replacement loop did not execute"
assert not thread.is_alive(), "replacement thread failed to exit"
assert monitor.status()["enabled"] is True
assert monitor.status()["health"]["state"] == "NOT_HEALTHY", "no real monitor cycle must never be healthy"
print("MONITOR_HARMLESS_THREAD_START_OK")
