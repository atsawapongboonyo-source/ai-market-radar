"""Offline route coverage contract; no scanner import, providers, or network calls."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def legacy_api_routes():
    tree = ast.parse((ROOT / "legacy_scanner.py").read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            fn = decorator.func
            if isinstance(fn, ast.Attribute) and fn.attr == "route" and isinstance(fn.value, ast.Name) and fn.value.id == "app":
                if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
                    route = decorator.args[0].value
                    if route.startswith("/api/"):
                        routes.add(route)
    return routes


class ScannerRouteCoverageTests(unittest.TestCase):
    def test_legacy_routes_have_safe_diagnostic_templates(self):
        from request_diagnostics_middleware import safe_path
        routes = legacy_api_routes()
        self.assertIn("/api/catalyst/<ticker>", routes)
        self.assertGreaterEqual(len(routes), 7)
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(safe_path({"radar.route_template": route}), route)

    def test_unknown_route_does_not_leak(self):
        from request_diagnostics_middleware import safe_path
        self.assertEqual(safe_path({"radar.route_template": "/api/private/<token>"}), "UNMAPPED")


if __name__ == "__main__":
    unittest.main()
