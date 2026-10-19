"""Offline release safety guard for opt-in request diagnostics.

Checks code structure only; it cannot attest to Render environment values,
live broker settings, or production rollback readiness.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
LOCKED_MODULES = (
    "legacy_scanner.py",
    "scanner_v410.py",
    "scanner_v510.py",
    "scanner_v520.py",
    "scanner_v530.py",
    "scanner_v531.py",
)

class ReleaseGuard(unittest.TestCase):
    def test_diagnostics_is_exact_opt_in(self):
        tree = ast.parse((ROOT / "scanner.py").read_text(encoding="utf-8"))
        checks = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
        found = False
        for node in checks:
            if not (len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
                    and len(node.comparators) == 1
                    and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == "1"):
                continue
            left = node.left
            if (isinstance(left, ast.Call)
                and isinstance(left.func, ast.Attribute)
                and left.func.attr == "get"
                and left.args
                and isinstance(left.args[0], ast.Constant)
                and left.args[0].value == "RADAR_REQUEST_DIAGNOSTICS"):
                found = True
        self.assertTrue(found, "diagnostics must be explicitly enabled with =1")

    def test_locked_modules_not_edited_in_diagnostics_branch(self):
        # GitHub CI checkout has origin/main; no network requests needed.
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        modified = set(result.stdout.splitlines())
        self.assertFalse(modified.intersection(LOCKED_MODULES),
                         "locked scanner modules changed: " + repr(modified.intersection(LOCKED_MODULES)))

    def test_no_unapproved_production_config(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        modified = set(result.stdout.splitlines())
        self.assertNotIn("render.yaml", modified)
        self.assertNotIn("requirements.txt", modified)
        self.assertNotIn("Procfile", modified)

if __name__ == "__main__":
    unittest.main()
