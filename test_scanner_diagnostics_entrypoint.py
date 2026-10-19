"""Offline import-boundary tests for the actual scanner.py compatibility entrypoint.

Stub legacy and V5.3.1 modules to avoid importing live market data or starting
background services. This tests the real scanner.py module, not a copy.
"""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch

from flask import Flask
from request_diagnostics_middleware import RequestDiagnosticsMiddleware


def load_entrypoint(enabled):
    legacy = types.ModuleType("legacy_scanner")
    legacy.SENTINEL = object()
    latest = types.ModuleType("scanner_v531")
    latest.app = Flask("scanner_diagnostics_boundary")
    with patch.dict(sys.modules, {"legacy_scanner": legacy, "scanner_v531": latest}):
        with patch.dict(os.environ, {"RADAR_REQUEST_DIAGNOSTICS": "1" if enabled else "0"}):
            name = "_scanner_diagnostics_boundary_test"
            spec = importlib.util.spec_from_file_location(name, "scanner.py")
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {name: module}):
                spec.loader.exec_module(module)
            return module, latest.app


class ScannerEntrypointBoundaryTests(unittest.TestCase):
    def test_disabled_preserves_wsgi_app(self):
        module, app = load_entrypoint(False)
        self.assertIs(module.app, app)
        self.assertNotIsInstance(app.wsgi_app, RequestDiagnosticsMiddleware)
        self.assertEqual(module.RUNTIME_VERSION, "5.3.1")

    def test_enabled_wraps_only_wsgi_boundary(self):
        module, app = load_entrypoint(True)
        self.assertIs(module.app, app)
        self.assertIsInstance(app.wsgi_app, RequestDiagnosticsMiddleware)
        self.assertTrue(app.wsgi_app.enabled)
        self.assertEqual(module.RUNTIME_VERSION, "5.3.1")
        self.assertEqual(len(app.before_request_funcs[None]), 1)


if __name__ == "__main__":
    unittest.main()
