import unittest
import test_capital_rotation_alpaca as fixtures
from capital_rotation_audit import audit_snapshot, compare_feeds


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AlpacaAdapterTests()
        self.fixture.setUp()
        self.snapshot = self.fixture.fetch()

    def test_recompute_and_close_timestamp(self):
        result = audit_snapshot(self.snapshot, expected_session=self.fixture.session)
        self.assertEqual(result['status'], 'PASSED')
        self.assertEqual(result['checks'][0]['20d']['base_close'], 100)
        self.assertEqual(self.snapshot['5d']['SPY']['asof_utc'], '2026-10-16T20:00:00+00:00')
        self.assertNotEqual(self.snapshot['5d']['SPY']['bar_timestamp_utc'], self.snapshot['5d']['SPY']['asof_utc'])

    def test_tampered_return_fails(self):
        self.snapshot['20d']['SPY']['return_pct'] += 1
        self.assertEqual(audit_snapshot(self.snapshot, expected_session=self.fixture.session)['status'], 'FAILED')

    def test_tampered_price_or_session_fails(self):
        self.snapshot['_observations']['SPY'][0]['close'] = 999
        self.assertEqual(audit_snapshot(self.snapshot, expected_session=self.fixture.session)['status'], 'FAILED')

    def test_cross_feed_has_explicit_limits(self):
        result = compare_feeds(self.snapshot, self.snapshot)
        self.assertFalse(result['independent_vendor'])
        self.assertEqual(result['checks'][0]['close_difference_bps'], 0)
