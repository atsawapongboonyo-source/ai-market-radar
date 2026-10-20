import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capital_rotation_alpaca import MarketDataError
from capital_rotation_alpaca_report import main


class AlpacaReportTests(unittest.TestCase):
    def test_provider_failure_replaces_previous_html(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'rotation.html'
            output.write_text('obsolete candidate list', encoding='utf-8')
            with patch('capital_rotation_alpaca_report.fetch_from_environment',
                       side_effect=MarketDataError('FEED_ACCESS_DENIED')):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = main(['2026-10-19', '--html', str(output)])
            self.assertEqual(result, 2)
            html = output.read_text(encoding='utf-8')
            self.assertIn('BLOCKED', html)
            self.assertIn('FEED_ACCESS_DENIED', html)
            self.assertNotIn('obsolete candidate', html)


if __name__ == '__main__':
    unittest.main()
