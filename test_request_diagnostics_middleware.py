import unittest
from request_diagnostics_middleware import RequestDiagnosticsMiddleware, safe_path


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.emit = lambda fmt, *args: self.logs.append(fmt % args)

    def test_disabled_does_not_log(self):
        def app(env, start):
            start("200 OK", [])
            return [b"ok"]
        middleware = RequestDiagnosticsMiddleware(app, emit=self.emit)
        self.assertEqual(list(middleware({}, lambda *a: None)), [b"ok"])
        self.assertEqual(self.logs, [])

    def test_success_has_start_and_end(self):
        def app(env, start):
            start("200 OK", [])
            return [b"ok"]
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        self.assertEqual(list(middleware({}, lambda *a: None)), [b"ok"])
        self.assertTrue(self.logs[0].startswith("REQUEST_START"))
        self.assertIn("status=200", self.logs[-1])

    def test_underlying_iterable_closed_once_on_consumption(self):
        counts = []
        class Body:
            def __iter__(self):
                yield b"ok"
            def close(self):
                counts.append("close")
        def app(env, start):
            start("200 OK", [])
            return Body()
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        response = middleware({}, lambda *a: None)
        self.assertEqual(list(response), [b"ok"])
        response.close()
        self.assertEqual(counts, ["close"])
        self.assertEqual(sum("REQUEST_END" in x for x in self.logs), 1)

    def test_underlying_iterable_closed_once_without_consumption(self):
        counts = []
        class Body:
            def __iter__(self):
                yield b"ok"
            def close(self):
                counts.append("close")
        def app(env, start):
            start("200 OK", [])
            return Body()
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        response = middleware({}, lambda *a: None)
        response.close()
        self.assertEqual(counts, ["close"])
        self.assertEqual(sum("REQUEST_END" in x for x in self.logs), 1)

    def test_sensitive_path_is_not_logged(self):
        self.assertEqual(safe_path({"PATH_INFO": "/token/secret"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/<symbol>"}), "/api/<symbol>")
        self.assertEqual(safe_path({"radar.route_template": "/api/scan"}), "/api/scan")
        self.assertEqual(safe_path({"radar.route_template": "/api/user-secret"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/<symbol>/private-secret"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/catalyst/<symbol>"}), "/api/catalyst/<symbol>")
        self.assertEqual(safe_path({"radar.route_template": "/private/account"}), "UNMAPPED")

    def test_app_exception_logs_and_reraises(self):
        def app(env, start):
            raise RuntimeError("private details")
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        with self.assertRaises(RuntimeError):
            middleware({}, lambda *a: None)
        self.assertIn("REQUEST_EXCEPTION", self.logs[-1])
        self.assertNotIn("private details", self.logs[-1])

    def test_stream_exception_logs_end(self):
        def app(env, start):
            start("200 OK", [])
            def generate():
                yield b"a"
                raise RuntimeError("stream failure")
            return generate()
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        with self.assertRaises(RuntimeError):
            list(middleware({}, lambda *a: None))
        self.assertTrue(any("REQUEST_STREAM_EXCEPTION" in log for log in self.logs))
        self.assertTrue(any("REQUEST_END" in log for log in self.logs))


if __name__ == "__main__":
    unittest.main()
