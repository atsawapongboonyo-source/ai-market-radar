import copy
import tempfile
import unittest

from capital_rotation_validation import compare_reference, archive_run, summarize_history
import test_capital_rotation_alpaca as fixtures


class ValidationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AlpacaAdapterTests()
        fixture.setUp()
        snapshot = fixture.fetch()
        self.evidence = {'expected_session': '2026-10-16',
                         'generated_utc': '2026-10-17T12:00:00+00:00',
                         'observations': snapshot['_observations'],
                         'result': {'status': 'RESEARCH_ONLY', 'candidates': [], 'trade_signal': False},
                         'calculation_audit': {'status': 'PASSED'}}
        rows = snapshot['_observations']['SPY']
        self.reference = {'expected_session': '2026-10-16', 'symbols': {'SPY': {
            'source_url': 'https://example.org/historical',
            'closes': {r['session']: r['close'] for r in (rows[-1], rows[-6], rows[-21])}}}}

    def test_sample_comparison_never_certifies_full_universe(self):
        result = compare_reference(self.evidence, self.reference)
        self.assertEqual(result['status'], 'SPOT_CHECK_ONLY')
        self.assertFalse(result['full_universe_verified'])
        self.assertFalse(result['adjustment_conventions_verified'])
        self.assertEqual(result['max_abs_close_difference_bps'], 0)

    def test_price_difference_is_exposed(self):
        self.reference['symbols']['SPY']['closes']['2026-10-16'] = 121
        result = compare_reference(self.evidence, self.reference)
        self.assertGreater(result['max_abs_close_difference_bps'], 80)
        self.assertGreater(result['max_abs_return_difference_pp'], 0)

    def test_stale_or_incomplete_reference_blocks(self):
        self.reference['expected_session'] = '2026-10-15'
        self.assertEqual(compare_reference(self.evidence, self.reference)['status'], 'BLOCKED')
        self.reference['expected_session'] = '2026-10-16'
        self.reference['symbols']['SPY']['closes'].pop('2026-10-16')
        self.assertEqual(compare_reference(self.evidence, self.reference)['status'], 'BLOCKED')

    def test_invalid_price_and_structure_block(self):
        self.reference['symbols']['SPY']['closes']['2026-10-16'] = float('nan')
        self.assertEqual(compare_reference(self.evidence, self.reference)['status'], 'BLOCKED')
        self.assertEqual(compare_reference(self.evidence, {'expected_session': '2026-10-16', 'symbols': None})['status'], 'BLOCKED')

    def test_repeated_runs_do_not_inflate_sessions_or_archive_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            evidence = dict(self.evidence, ALPACA_DATA_SECRET_KEY='synthetic-forbidden-field')
            archive_run(evidence, root)
            archive_run(evidence, root)
            later = copy.deepcopy(evidence)
            later['generated_utc'] = '2026-10-17T13:00:00+00:00'
            summary = archive_run(later, root)
            self.assertEqual(summary['distinct_sessions'], 1)
            self.assertEqual(summary['consecutive_sessions'], 1)
            from pathlib import Path
            for file in Path(root).glob('*/*.json'):
                self.assertNotIn('synthetic-forbidden-field', file.read_text(encoding='utf-8'))

    def test_gap_and_blocked_run_do_not_count_as_consecutive(self):
        with tempfile.TemporaryDirectory() as root:
            archive_run(self.evidence, root)
            later = copy.deepcopy(self.evidence)
            later.update(expected_session='2026-10-20', generated_utc='2026-10-21T12:00:00+00:00')
            summary = archive_run(later, root)
            self.assertEqual(summary['distinct_sessions'], 2)
            self.assertEqual(summary['consecutive_sessions'], 1)
            blocked = copy.deepcopy(self.evidence)
            blocked.update(expected_session='2026-10-19', generated_utc='2026-10-20T12:00:00+00:00')
            blocked['result']['status'] = 'BLOCKED'
            summary = archive_run(blocked, root)
            self.assertEqual(summary['consecutive_sessions'], 1)
            self.assertEqual(summary['status'], 'IN_PROGRESS')

    def test_conflicting_run_cannot_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            archive_run(self.evidence, root)
            changed = copy.deepcopy(self.evidence)
            changed['result']['status'] = 'BLOCKED'
            with self.assertRaisesRegex(ValueError, 'conflicting run timestamp'):
                archive_run(changed, root)
