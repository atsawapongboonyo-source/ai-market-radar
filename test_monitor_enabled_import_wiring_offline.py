"""Verify monitor-enabled import wiring without starting its background thread.

Thread.start is intercepted BEFORE scanner imports; no monitor cycles, market
data fetches, alerts or broker actions can execute. This tests only startup
registration, not live monitor operation or production safety.
"""
import os
import threading

assert os.environ.get("SERVER_AUTO_MONITOR_ENABLED") == "1"
assert os.environ.get("TELEGRAM_TEST_ON_BOOT") == "0"
assert os.environ.get("LIVE_TRADING") == "0"
assert os.environ.get("RADAR_REQUEST_DIAGNOSTICS") in {"0", "1"}

started = []
original_start = threading.Thread.start

def intercept_start(self, *args, **kwargs):
    started.append(self)
    if self.name == "ai-radar-server-monitor":
        return None
    raise AssertionError("unexpected thread startup: " + self.name)

threading.Thread.start = intercept_start
try:
    import scanner
finally:
    threading.Thread.start = original_start

from flask import Flask
from request_diagnostics_middleware import RequestDiagnosticsMiddleware
assert isinstance(scanner.app, Flask)
assert scanner.RUNTIME_VERSION == "5.3.1"
assert len(started) == 1, [(t.name, t.daemon) for t in started]
assert started[0].name == "ai-radar-server-monitor"
assert not started[0].is_alive()
assert isinstance(scanner.app.wsgi_app, RequestDiagnosticsMiddleware) == (
    os.environ["RADAR_REQUEST_DIAGNOSTICS"] == "1"
)
with scanner.app.test_client() as client:
    response = client.get("/api/server-monitor-status")
    assert response.status_code == 200 and response.is_json
    data = response.get_json()["data"]
    assert data["enabled"] is True
    assert data["running"] is True  # Registration state, not actual thread liveness.
print("MONITOR_ENABLED_IMPORT_WIRING_OK diagnostics=" +
      os.environ["RADAR_REQUEST_DIAGNOSTICS"])
