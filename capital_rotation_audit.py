"""Independent decimal recomputation and optional cross-feed evidence.

Provider closes only; no credentials or HTTP objects are accepted/serialized.
Cross-feed differences are descriptive: IEX and SIP cover different markets.
"""
from decimal import Decimal, InvalidOperation
from capital_rotation_alpaca import SYMBOLS
from capital_rotation_calendar import trailing_sessions


def audit_snapshot(snapshot, *, expected_session):
    checks = []
    try:
        days = [d.isoformat() for d in trailing_sessions(expected_session)]
        for symbol in SYMBOLS:
            rows = snapshot['_observations'][symbol]
            if [row['session'] for row in rows] != days:
                raise ValueError('sessions')
            closes = [Decimal(str(row['close'])) for row in rows]
            if any(not c.is_finite() or c <= 0 for c in closes):
                raise ValueError('closes')
            item = {'symbol': symbol, 'close': float(closes[-1])}
            for window, offset in (('5d', 5), ('20d', 20)):
                actual = (closes[-1] / closes[-1-offset] - 1) * 100
                reported = Decimal(str(snapshot[window][symbol]['return_pct']))
                if not reported.is_finite() or abs(actual - reported) > Decimal('0.000000001'):
                    raise ValueError('returns')
                item[window] = {'base_session': days[-1-offset],
                                'base_close': float(closes[-1-offset]),
                                'return_pct': float(actual)}
            checks.append(item)
    except (KeyError, TypeError, ValueError, IndexError, InvalidOperation):
        return {'status': 'FAILED', 'reason': 'OBSERVATION_OR_RETURN_MISMATCH', 'checks': []}
    return {'status': 'PASSED', 'method': 'Decimal recomputation from 21 provider closes',
            'independent_market_source': False, 'checks': checks}


def compare_feeds(primary, reference):
    rows = []
    for symbol in SYMBOLS:
        a = primary['_observations'][symbol][-1]['close']
        b = reference['_observations'][symbol][-1]['close']
        rows.append({'symbol': symbol, 'iex_close': a, 'sip_close': b,
                     'close_difference_bps': (a / b - 1) * 10000,
                     'return_5d_difference_pp': primary['5d'][symbol]['return_pct'] - reference['5d'][symbol]['return_pct'],
                     'return_20d_difference_pp': primary['20d'][symbol]['return_pct'] - reference['20d'][symbol]['return_pct']})
    return {'status': 'COMPARED', 'independent_vendor': False,
            'note': 'Same provider, different market coverage; differences are not necessarily errors.',
            'checks': rows}
