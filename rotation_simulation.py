"""Synthetic public summaries for separately labeled staging services only."""
from capital_rotation_calendar import last_completed_session
from rotation_public_protocol import SYMBOLS


def simulated_publication(now):
    values = {s: (1 if s == 'SPY' else 0 if s in ('SMH', 'SOXX') else 3) for s in SYMBOLS}
    return {'schema_version': 1, 'session_date': last_completed_session(now).isoformat(),
            'generated_utc': now.isoformat(), 'feed': 'iex',
            'returns': {w: dict(values) for w in ('5d', '20d')}}
