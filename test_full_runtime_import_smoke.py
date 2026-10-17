"""Real scanner:app import smoke in an isolated CI process.

CI MUST run this script with outbound networking denied at the runner/container
boundary. No live market endpoints or broker actions are invoked here.
"""
import os
import sys
import threading

for name in ("SERVER_AUTO_MONITOR_ENABLED", "TELEGRAM_TEST_ON_BOOT", "LIVE_TRADING"):
    if os.environ.get(name) != "0":
        raise SystemExit("unsafe environment: " + name + " must equal 0")

from flask import Flask
import scanner

assert isinstance(scanner.app, Flask), "scanner.app is not a Flask application"
assert scanner.RUNTIME_VERSION == "5.3.1"
routes = {rule.rule for rule in scanner.app.url_map.iter_rules()}
for route in ("/api/scan", "/api/multi-radar", "/api/server-monitor-status"):
    assert route in routes, "missing route: " + route

from request_diagnostics_middleware import RequestDiagnosticsMiddleware
enabled = os.environ.get("RADAR_REQUEST_DIAGNOSTICS") == "1"
assert isinstance(scanner.app.wsgi_app, RequestDiagnosticsMiddleware) == enabled
assert not any(t.name == "ai-radar-server-monitor" for t in threading.enumerate())
print("FULL_RUNTIME_IMPORT_OK diagnostics=" + str(enabled) + " routes=" + str(len(routes)))

# Read-only API parity contract. This endpoint reads in-memory monitor state;
# it does not fetch market data, refresh scanner rankings, or submit orders.
with scanner.app.test_client() as client:
    response = client.get("/api/server-monitor-status")
    assert response.status_code == 200, "monitor status HTTP changed"
    assert response.is_json, "monitor status must remain JSON"
    payload = response.get_json()
    assert payload.get("ok") is True, "monitor status response not ok"
    assert payload.get("version") == "5.3", "monitor status version changed"
    state = payload.get("data")
    assert isinstance(state, dict), "monitor state missing"
    assert state.get("enabled") is False, "monitor unexpectedly enabled"
    assert state.get("running") is False, "monitor unexpectedly running"
    assert "candidates" in state, "monitor candidates contract missing"
print("READ_ONLY_API_PARITY_OK diagnostics=" + str(enabled))
