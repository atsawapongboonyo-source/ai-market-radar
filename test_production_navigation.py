"""Navigation isolation checks; never call scan/refresh or market-data APIs."""
import unittest
from flask import Response
import scanner


class ProductionNavigationTests(unittest.TestCase):
    def test_real_pages_only_add_one_navigation_element(self):
        app = scanner.app
        hook = scanner.rotation_staging_backlink
        hooks = app.after_request_funcs[None]
        for path in ('/', '/scanner', '/analysis'):
            with self.subTest(path=path):
                hooks.remove(hook)
                try:
                    original = app.test_client().get(path)
                finally:
                    hooks.append(hook)
                changed = app.test_client().get(path)
                self.assertEqual(original.status_code, 200)
                body = changed.get_data(as_text=True)
                start = body.index('<nav id="rotation-staging-backlink"')
                end = body.index('</nav>', start) + len('</nav>')
                self.assertEqual(body[:start] + body[end:], original.get_data(as_text=True))
                self.assertEqual(body.count('id="rotation-staging-backlink"'), 1)
                self.assertIn('Capital Rotation (Staging)', body[start:end])
                self.assertIn('https://ai-market-radar-rotation-staging.onrender.com/rotation', body[start:end])
                self.assertEqual(int(changed.headers['Content-Length']), len(changed.data))

    def test_api_errors_redirects_and_streams_remain_untouched(self):
        cases = [('/api/scan', 200, 'application/json', False),
                 ('/api/rotation/ingest', 401, 'application/json', False),
                 ('/', 500, 'text/html', False), ('/', 302, 'text/html', False),
                 ('/other', 200, 'text/html', False), ('/', 200, 'text/plain', False),
                 ('/', 200, 'text/html', True)]
        for path, status, mime, streaming in cases:
            with self.subTest(path=path, status=status, mime=mime, streaming=streaming):
                with scanner.app.test_request_context(path):
                    response = Response('<body>unchanged</body>', status=status, mimetype=mime)
                    before = response.get_data(), list(response.headers)
                    response.direct_passthrough = streaming
                    result = scanner.rotation_staging_backlink(response)
                    result.direct_passthrough = False
                    self.assertIs(result, response)
                    self.assertEqual((result.get_data(), list(result.headers)), before)

    def test_duplicate_injection_and_request_values(self):
        with scanner.app.test_request_context('/?next=%3Cscript%3Ebad%3C/script%3E'):
            response = Response('<body>original</body>', mimetype='text/html')
            once = scanner.rotation_staging_backlink(response).get_data()
            twice = scanner.rotation_staging_backlink(response).get_data()
            self.assertEqual(once, twice)
            self.assertNotIn(b'<script>', twice)


if __name__ == '__main__':
    unittest.main()
