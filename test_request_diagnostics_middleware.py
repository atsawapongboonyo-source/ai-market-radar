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
        self.assertEqual(safe_path({"radar.route_template": "/api/<symbol>"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/scan"}), "/api/scan")
        self.assertEqual(safe_path({"radar.route_template": "/api/user-secret"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/<symbol>/private-secret"}), "UNMAPPED")
        self.assertEqual(safe_path({"radar.route_template": "/api/catalyst/<ticker>"}), "/api/catalyst/<ticker>")
        for template in ("/api/scan/refresh", "/api/auto-confirm", "/api/opening-confirm", "/api/position-manage"):
            self.assertEqual(safe_path({"radar.route_template": template}), template)
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

    def test_early_close_after_first_chunk_logs_once(self):
        closed = []
        def app(env, start):
            start("200 OK", [])
            class Body:
                def __iter__(self):
                    yield b"first"
                    yield b"second"
                def close(self):
                    closed.append(True)
            return Body()
        response = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)(
            {"PATH_INFO": "/private/secret", "QUERY_STRING": "token=secret"},
            lambda *args: None,
        )
        iterator = iter(response)
        self.assertEqual(next(iterator), b"first")
        response.close()
        response.close()
        self.assertEqual(len(closed), 1)
        self.assertEqual(sum("REQUEST_END" in line for line in self.logs), 1)
        self.assertNotIn("secret", "\n".join(self.logs))

    def test_response_status_does_not_log_headers(self):
        def app(env, start):
            start("503 Service Unavailable", [("Set-Cookie", "secret-cookie")])
            return [b"unavailable"]
        response = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)(
            {"radar.route_template": "/api/scan"}, lambda *args: None
        )
        self.assertEqual(list(response), [b"unavailable"])
        self.assertTrue(any("status=503" in line for line in self.logs))
        self.assertNotIn("secret-cookie", "\n".join(self.logs))


    def test_exception_before_response_does_not_log_private_details(self):
        def app(env, start):
            raise ValueError("credential=never-log-this")
        middleware = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)
        with self.assertRaisesRegex(ValueError, "credential=never-log-this"):
            middleware({"PATH_INFO": "/private/secret"}, lambda *args: None)
        self.assertEqual(sum("REQUEST_START" in line for line in self.logs), 1)
        self.assertEqual(sum("REQUEST_EXCEPTION" in line for line in self.logs), 1)
        self.assertEqual(sum("REQUEST_END" in line for line in self.logs), 0)
        self.assertNotIn("never-log-this", "\n".join(self.logs))

    def test_close_without_iteration_twice_is_idempotent(self):
        closed = []
        class Body:
            def __iter__(self):
                yield b"unused"
            def close(self):
                closed.append(1)
        def app(env, start):
            start("200 OK", [])
            return Body()
        response = RequestDiagnosticsMiddleware(app, enabled=True, emit=self.emit)(
            {}, lambda *args: None
        )
        response.close()
        response.close()
        self.assertEqual(closed, [1])
        self.assertEqual(sum("REQUEST_END" in line for line in self.logs), 1)



if __name__ == "__main__":
    unittest.main()
