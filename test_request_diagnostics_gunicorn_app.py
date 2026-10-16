"""Small isolated WSGI app for Gunicorn diagnostics smoke tests."""
import os
from flask import Flask, request
from request_diagnostics_middleware import RequestDiagnosticsMiddleware

app = Flask(__name__)

@app.before_request
def route_template():
    if request.url_rule is not None:
        request.environ["radar.route_template"] = request.url_rule.rule

@app.get("/api/scan")
def scan():
    return {"ok": True}

@app.get("/api/catalyst/<ticker>")
def catalyst(symbol):
    return {"symbol": symbol}

@app.get("/private/<secret>")
def private(secret):
    return {"ok": True}

if os.environ.get("RADAR_REQUEST_DIAGNOSTICS") == "1":
    app.wsgi_app = RequestDiagnosticsMiddleware(app.wsgi_app, enabled=True)
