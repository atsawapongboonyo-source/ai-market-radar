import unittest
from capital_rotation_html import render_rotation_html


class RotationHtmlTests(unittest.TestCase):
    def test_read_only_candidates(self):
        html = render_rotation_html({
            "expected_session": "2026-10-16", "generated_utc": "2026-10-17T00:00:00Z",
            "result": {"status": "RESEARCH_ONLY", "regime": "CONFIRMED_RELATIVE_ROTATION",
                       "candidates": [{"symbol": "XLV", "relative_5d_pct": 2.5,
                                       "relative_20d_pct": 4.5}]}
        })
        self.assertIn("XLV", html)
        self.assertIn("4.5", html)
        self.assertIn("Research Only", html)

    def test_blocked_hides_candidates_and_escapes_untrusted_text(self):
        html = render_rotation_html({
            "result": {"status": "BLOCKED", "reason": "<script>alert(1)</script>",
                       "candidates": [{"symbol": "XLV", "relative_5d_pct": 1}]}
        })
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<td>XLV</td>", html)

    def test_candidate_symbol_is_escaped(self):
        html = render_rotation_html({
            "result": {"status": "RESEARCH_ONLY",
                       "candidates": [{"symbol": "<img src=x onerror=alert(1)>"}]}
        })
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)


if __name__ == "__main__":
    unittest.main()
