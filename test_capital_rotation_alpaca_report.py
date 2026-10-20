import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from capital_rotation_alpaca import MarketDataError
from capital_rotation_alpaca_report import main


class AlpacaReportTests(unittest.TestCase):
    def setUp(self):
        clock = patch('capital_rotation_alpaca_report.datetime')
        self.clock = clock.start()
        self.clock.now.return_value = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        self.addCleanup(clock.stop)

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

    def test_auto_calendar_success_and_sip_denial_retains_research_label(self):
        from test_capital_rotation_alpaca import AlpacaAdapterTests
        from datetime import date
        import json
        fixture = AlpacaAdapterTests()
        fixture.setUp()
        self.clock.now.return_value = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        with patch('capital_rotation_alpaca_report.fetch_from_environment',
                   side_effect=[fixture.fetch(), MarketDataError('FEED_ACCESS_DENIED')]) as fetch:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main(['--verify-sip'])
        self.assertEqual(result, 0)
        self.assertEqual(fetch.call_args_list[0].kwargs['expected_session'], date(2026, 10, 16))
        report = json.loads(output.getvalue())
        self.assertEqual(report['calculation_audit']['status'], 'PASSED')
        self.assertEqual(report['cross_feed_verification']['status'], 'BLOCKED')
        self.assertEqual(report['result']['status'], 'RESEARCH_ONLY')

    def test_manual_stale_session_never_fetches(self):
        with patch('capital_rotation_alpaca_report.fetch_from_environment') as fetch:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['2026-10-16']), 2)
        fetch.assert_not_called()
        self.assertIn('NOT_LATEST_COMPLETED_SESSION', output.getvalue())

    def test_evidence_contains_prices_and_recomputable_returns(self):
        import json
        from test_capital_rotation_alpaca import AlpacaAdapterTests
        fixture = AlpacaAdapterTests()
        fixture.setUp()
        self.clock.now.return_value = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / 'audit.json'
            with patch('capital_rotation_alpaca_report.fetch_from_environment', return_value=fixture.fetch()):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--audit-json', str(evidence)]), 0)
            payload = json.loads(evidence.read_text(encoding='utf-8'))
            self.assertEqual(len(payload['observations']['SPY']), 21)
            self.assertEqual(payload['calculation_audit']['status'], 'PASSED')
            self.assertEqual(payload['cross_feed_verification']['status'], 'NOT_RUN')
            self.assertNotIn('test-secret', evidence.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
