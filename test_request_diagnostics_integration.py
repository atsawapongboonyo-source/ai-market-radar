import ast
import pathlib
import unittest


class OptInIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(pathlib.Path("scanner.py").read_text(encoding="utf-8"))

    def test_opt_in_is_explicit_string_one(self):
        checks = [n for n in ast.walk(self.tree) if isinstance(n, ast.Compare)
                  and any(isinstance(x, ast.Constant) and x.value == "1"
                          for x in n.comparators)]
        self.assertTrue(checks, "Diagnostic gate must explicitly require value 1")

    def test_wsgi_wrapper_is_inside_conditional(self):
        wrapping = [n for n in ast.walk(self.tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Attribute) and t.attr == "wsgi_app"
                            for t in n.targets)]
        self.assertEqual(len(wrapping), 1)
        conditionals = [n for n in ast.walk(self.tree) if isinstance(n, ast.If)]
        self.assertTrue(any(wrapping[0] in n.body for n in conditionals),
                        "WSGI wrapper must not be installed unconditionally")


if __name__ == "__main__":
    unittest.main()
