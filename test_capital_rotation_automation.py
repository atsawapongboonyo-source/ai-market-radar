import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from capital_rotation_alpaca import SYMBOLS, MarketDataError, _daily_close_snapshot
from capital_rotation_automation import run_once, next_market_due, valid_saved
from capital_rotation_calendar import trailing_sessions
from capital_rotation_storage import atomic_write_text


def snapshot_for(day):
    days = trailing_sessions(day)
    return _daily_close_snapshot({'bars': {s: [
        {'t': d.isoformat() + 'T04:00:00Z', 'c': 100 + i}
        for i, d in enumerate(days)] for s in SYMBOLS}}, expected_session=day)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        self.calls = []

    def fetch(self, *, expected_session, feed):
        self.assertEqual(feed, 'iex')
        self.calls.append(expected_session)
        return snapshot_for(expected_session)

    def test_initial_run_fourteen_by_twenty_one_and_no_duplicate_fetch(self):
        health = run_once(self.root, now=self.now, fetcher=self.fetch)
        self.assertEqual(health['status'], 'OK')
        self.assertEqual((health['symbols'], health['sessions_per_symbol']), (14, 21))
        health2 = run_once(self.root, now=self.now + timedelta(minutes=15), fetcher=self.fetch)
        self.assertEqual(health2['status'], 'UP_TO_DATE')
        self.assertEqual(self.calls, [date(2026, 10, 19)])
        self.assertEqual(len(list((self.root / 'daily').glob('*.json'))), 1)
        self.assertIn('Health Status', (self.root / 'rotation-dashboard.html').read_text(encoding='utf-8'))

    def test_catch_up_fills_missing_days_without_overwriting_previous_day(self):
        run_once(self.root, now=self.now, fetcher=self.fetch)
        first = self.root / 'daily' / '2026-10-19.json'
        saved = first.read_bytes()
        later = datetime(2026, 10, 22, 21, tzinfo=timezone.utc)
        health = run_once(self.root, now=later, fetcher=self.fetch)
        self.assertEqual(health['downloaded_sessions'], ['2026-10-20', '2026-10-21', '2026-10-22'])
        self.assertEqual(first.read_bytes(), saved)
        historical = json.loads((self.root / 'daily' / '2026-10-20.json').read_text())
        self.assertTrue(historical['historical_catch_up'])
        self.assertNotEqual(historical['evaluation_utc'], historical['generated_utc'])

    def test_provider_failure_hides_previous_candidates_and_never_leaks_text(self):
        run_once(self.root, now=self.now, fetcher=self.fetch)
        def broken(**kwargs):
            raise RuntimeError('synthetic-secret-never-print')
        health = run_once(self.root, now=self.now + timedelta(days=1), fetcher=broken)
        self.assertEqual(health['status'], 'BLOCKED')
        self.assertEqual(health['error_code'], 'INTERNAL_ERROR')
        html = (self.root / 'rotation-dashboard.html').read_text(encoding='utf-8')
        self.assertIn('BLOCKED', html)
        for file in self.root.glob('*'):
            if file.is_file():
                self.assertNotIn('synthetic-secret-never-print', file.read_text(encoding='utf-8'))

    def test_partial_snapshot_fail_closed_no_daily_file(self):
        def incomplete(**kwargs):
            snapshot = snapshot_for(kwargs['expected_session'])
            del snapshot['_observations']['XLV']
            return snapshot
        health = run_once(self.root, now=self.now, fetcher=incomplete)
        self.assertEqual(health['error_code'], 'CALCULATION_AUDIT_FAILED')
        self.assertFalse((self.root / 'daily').exists())

    def test_corrupt_or_forged_saved_classification_is_refetched(self):
        run_once(self.root, now=self.now, fetcher=self.fetch)
        path = self.root / 'daily' / '2026-10-19.json'
        data = json.loads(path.read_text())
        data['result']['regime'] = 'FORGED'
        path.write_text(json.dumps(data))
        run_once(self.root, now=self.now, fetcher=self.fetch)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(valid_saved(json.loads(path.read_text()), date(2026, 10, 19)))

    def test_missing_credentials_preflight_writes_blocked_dashboard(self):
        health = run_once(self.root, now=self.now, fetcher=self.fetch, forced_error='CREDENTIALS_UNAVAILABLE')
        self.assertEqual(health['error_code'], 'CREDENTIALS_UNAVAILABLE')
        self.assertEqual(self.calls, [])

    def test_long_downtime_alerts_instead_of_silently_skipping_history(self):
        (self.root / 'health.json').write_text(json.dumps({'last_success_session': '2026-08-03'}))
        health = run_once(self.root, now=self.now, fetcher=self.fetch)
        self.assertEqual(health['error_code'], 'CATCH_UP_LIMIT_EXCEEDED')
        self.assertEqual(self.calls, [])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI and PowerShell')
    def test_windows_dpapi_wrapper_does_not_forward_child_secret_output(self):
        import subprocess
        import sys
        script = Path(__file__).parent / 'scripts' / 'rotation-windows-offline-test.ps1'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-File', str(script), '-TestRoot', str(self.root),
            '-PythonPath', sys.executable], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('WINDOWS_OFFLINE_OK', result.stdout)
        self.assertNotIn('synthetic-child-secret', result.stdout + result.stderr)

    def test_calendar_unknown_year_fails_without_provider_request(self):
        health = run_once(self.root, now=datetime(2029, 1, 3, tzinfo=timezone.utc), fetcher=self.fetch)
        self.assertEqual(health['status'], 'BLOCKED')
        self.assertEqual(self.calls, [])

    def test_next_due_holiday_early_close_and_dst(self):
        self.assertEqual(next_market_due(datetime(2026, 11, 26, 12, tzinfo=timezone.utc)),
                         datetime(2026, 11, 27, 18, 20, tzinfo=timezone.utc))
        self.assertEqual(next_market_due(datetime(2026, 10, 30, 21, tzinfo=timezone.utc)),
                         datetime(2026, 11, 2, 21, 20, tzinfo=timezone.utc))

    def test_atomic_failure_preserves_previous_file_and_cleans_temporary(self):
        output = self.root / 'report.html'
        atomic_write_text(output, 'old report')
        with patch('capital_rotation_storage.os.replace', side_effect=OSError('disk fault')):
            with self.assertRaises(OSError):
                atomic_write_text(output, 'new report')
        self.assertEqual(output.read_text(), 'old report')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_atomic_create_cannot_overwrite_previous_history(self):
        output = self.root / 'history.json'
        atomic_write_text(output, 'one', overwrite=False)
        with self.assertRaises(FileExistsError):
            atomic_write_text(output, 'two', overwrite=False)
        self.assertEqual(output.read_text(), 'one')

    @unittest.skipUnless(os.name == 'nt', 'Windows file locking')
    def test_os_lock_prevents_concurrent_runs_and_releases(self):
        from capital_rotation_automation import run_lock
        with run_lock(self.root) as first:
            self.assertTrue(first)
            with run_lock(self.root) as second:
                self.assertFalse(second)
        with run_lock(self.root) as third:
            self.assertTrue(third)


if __name__ == '__main__':
    unittest.main()
