"""Exercise diagnostics through a real Flask WSGI request lifecycle, offline."""
import unittest

from flask import Flask, request
from request_diagnostics_middleware import RequestDiagnosticsMiddleware


def make_app(enabled, messages):
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.before_request
    def route_template():
        if request.url_rule is not None:
            request.environ["radar.route_template"] = request.url_rule.rule

    @app.get("/api/scan")
    def scan():
        return {"ok": True}

    @app.get("/api/catalyst/<symbol>")
    def catalyst(symbol):
        return {"ok": True, "symbol": symbol}

    @app.get("/private/<secret>")
    def private(secret):
        return {"ok": True}

    app.wsgi_app = RequestDiagnosticsMiddleware(
        app.wsgi_app, enabled=enabled,
        emit=lambda fmt, *args: messages.append(fmt % args))
    return app


class RequestDiagnosticsEndToEndTests(unittest.TestCase):
    def test_off_keeps_response_and_emits_nothing(self):
        messages = []
        with make_app(False, messages).test_client() as client:
            response = client.get("/api/scan?token=not-for-logs")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertEqual(messages, [])

    def test_on_records_template_not_symbol_or_query(self):
        messages = []
        with make_app(True, messages).test_client() as client:
            response = client.get("/api/catalyst/SECRET-SYMBOL?token=PRIVATE")
        self.assertEqual(response.status_code, 200)
        response.close()
        combined = "\n".join(messages)
        self.assertIn("route=/api/catalyst/<symbol>", combined)
        self.assertIn("REQUEST_START", combined)
        self.assertIn("REQUEST_END", combined)
        self.assertNotIn("SECRET-SYMBOL", combined)
        self.assertNotIn("PRIVATE", combined)

    def test_on_private_route_is_unmapped(self):
        messages = []
        with make_app(True, messages).test_client() as client:
            response = client.get("/private/secret-value")
        self.assertEqual(response.status_code, 200)
        combined = "\n".join(messages)
        self.assertIn("route=UNMAPPED", combined)
        self.assertNotIn("secret-value", combined)

    def test_on_404_has_status_and_no_path(self):
        messages = []
        with make_app(True, messages).test_client() as client:
            response = client.get("/missing/SECRET?token=PRIVATE")
        self.assertEqual(response.status_code, 404)
        combined = "\n".join(messages)
        self.assertIn("status=404", combined)
        self.assertNotIn("SECRET", combined)
        self.assertNotIn("PRIVATE", combined)


if __name__ == "__main__":
    unittest.main()
