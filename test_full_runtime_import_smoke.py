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
