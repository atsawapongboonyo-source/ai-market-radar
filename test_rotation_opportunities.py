"""Synthetic projection tests; never market publications."""
import json
from datetime import timedelta
from flask import Flask
from test_rotation_stock import NOW, StockContractTests, universe
from rotation_stock_protocol import parse_stock
from rotation_public_protocol import PublicDataError
from rotation_opportunities import opportunities, install_opportunities


def current(now=NOW):
    raw = json.dumps(StockContractTests().payload()).encode()
    try:
        return {'status': 'RESEARCH_ONLY', **parse_stock(raw, now, universe())}
    except PublicDataError as e:
        return {'status': 'BLOCKED', 'reason': str(e), 'stocks': []}


def test_actual_states_only_and_no_claim_of_live_confidence_or_holdings():
    d = opportunities(current, NOW)
    assert d['counts']['READY'] == 0
    assert d['status'] == 'WAIT'
    assert d['cards'][0]['state'] == current()['stocks'][0]['state']
    assert 'NOT LIVE' in d['source'] and 'not consolidated SIP' in d['source']
    assert d['cards'][0]['confidence'] == 'NOT_CALIBRATED'
    assert d['guard']['status'] == 'UNKNOWN' and not d['trade_signal']
    assert d['last_quote_utc'] is None and d['last_trade_utc'] is None


def test_stale_snapshot_hides_all_opportunities():
    d = opportunities(lambda: current(NOW + timedelta(days=1)), NOW + timedelta(days=1))
    assert d['status'] == 'BLOCKED' and d['cards'] == []
    assert d['reason'] == 'STALE_SESSION'


def test_projection_preserves_ready_wait_avoid_blocked_without_promotion():
    base = current()
    row = base['stocks'][0]
    # Labelled synthetic projection fixtures only. Production current() validates rules.
    base['stocks'] = [{**row, 'state': s} for s in ('READY', 'WAIT', 'AVOID', 'BLOCKED')]
    d = opportunities(lambda: base, NOW)
    assert d['counts'] == dict.fromkeys(('READY', 'WAIT', 'AVOID', 'BLOCKED'), 1)
    assert [r['state'] for r in d['cards']] == ['READY', 'WAIT', 'AVOID', 'BLOCKED']


def test_home_only_escape_no_scanner_view_change_or_market_calls():
    scanner = Flask('opportunity-scanner-test')
    rotation = Flask('opportunity-rotation-test')
    scanner.add_url_rule('/', 'home', lambda: '<html><body>home</body></html>')
    scanner.add_url_rule('/scanner', 'scanner', lambda: '<html><body>scanner</body></html>')
    before = dict(scanner.view_functions)
    install_opportunities(scanner, rotation, current, lambda: NOW)
    assert scanner.view_functions == before
    assert b'Radar Opportunities' in scanner.test_client().get('/').data
    assert b'Radar Opportunities' not in scanner.test_client().get('/scanner').data
    response = rotation.test_client().get('/api/rotation/opportunities')
    assert response.json['counts']['READY'] == 0
    assert response.headers['Cache-Control'] == 'no-store'
    assert rotation.test_client().post('/api/rotation/opportunities').status_code == 405


def test_all_avoid_is_not_wait_and_unknown_calendar_blocks():
    data = current()
    data['stocks'][0]['state'] = 'AVOID'  # synthetic projection only
    assert opportunities(lambda: data, NOW)['status'] == 'AVOID'
    d = opportunities(lambda: data, NOW.replace(year=2029))
    assert d['status'] == 'BLOCKED' and not d['cards']
