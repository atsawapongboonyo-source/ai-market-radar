"""Offline Flask contract tests: research UI never evaluates, fetches or trades."""
import unittest
from flask import Flask
from rotation_navigation import install_navigation
from stock_radar_research_web import install_research_directory, filtered_rows
from stock_radar_universe_validation import WATCHLIST
import json

class StockRadarResearchWebTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        install_research_directory(self.app)
        install_navigation(self.app)
        self.client = self.app.test_client()

    def test_search_and_filter(self):
        r = self.client.get('/stock-radar?q=MU')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'MU', r.data)
        self.assertIn(b'NOT_EVALUATED', r.data)
        self.assertIn(b'capital-rotation-nav', r.data)
        self.assertIn(b'href="/stock-radar"', r.data)
        self.assertNotIn(b'READY</td>', r.data)
        self.assertIn('no-store', r.headers['Cache-Control'])

    def test_group_filter_and_no_results(self):
        r = self.client.get('/stock-radar?group=Cybersecurity')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'CRWD', r.data)
        self.assertNotIn(b'AXTI</strong>', r.data)
        self.assertIn(b'No candidates', self.client.get('/stock-radar?q=NO_MATCH_SYMBOL').data)

    def test_escaping_and_invalid_group(self):
        r = self.client.get('/stock-radar?q=%3Cscript%3E&group=UNKNOWN')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b'<script>', r.data)
        watchlist = json.loads(WATCHLIST.read_text(encoding='utf-8'))
        self.assertEqual(len(filtered_rows(watchlist, group='UNKNOWN')), 40)

if __name__ == '__main__':
    unittest.main()
