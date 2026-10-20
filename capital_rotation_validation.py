"""Offline price spot checks and local research-run history. No downloads."""
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
import json

from capital_rotation_calendar import CalendarError, trailing_sessions, is_session
from capital_rotation_storage import atomic_write_text


def compare_reference(evidence, reference):
    """Describe sampled external closes; never certify unmatched conventions."""
    failed = {'status': 'BLOCKED', 'reason': 'INVALID_REFERENCE', 'checks': []}
    try:
        if reference['expected_session'] != evidence['expected_session']:
            return dict(failed, reason='REFERENCE_SESSION_MISMATCH')
        session = date.fromisoformat(evidence['expected_session'])
        days = trailing_sessions(session)
        dates = [days[-1].isoformat(), days[-6].isoformat(), days[-21].isoformat()]
        checks = []
        for symbol, sample in reference['symbols'].items():
            url = sample['source_url']
            if not isinstance(url, str) or not url.startswith('https://'):
                return failed
            observed = {r['session']: r['close'] for r in evidence['observations'][symbol]}
            points = []
            for day in dates:
                a, b = observed[day], sample['closes'][day]
                if any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not isfinite(v) or v <= 0 for v in (a, b)):
                    return failed
                points.append({'session': day, 'iex_close': a, 'reference_close': b,
                               'difference_bps': (a / b - 1) * 10000})
            returns = {}
            for window, base in (('5d', dates[1]), ('20d', dates[2])):
                a = (observed[dates[0]] / observed[base] - 1) * 100
                b = (sample['closes'][dates[0]] / sample['closes'][base] - 1) * 100
                returns[window] = {'iex_pct': a, 'reference_pct': b,
                                   'difference_pp': a - b}
            checks.append({'symbol': symbol, 'source_url': url,
                           'closes': points, 'returns': returns})
        if not checks:
            return failed
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return failed
    return {'status': 'SPOT_CHECK_ONLY', 'full_universe_verified': False,
            'adjustment_conventions_verified': False,
            'note': 'External published close sample; feed and corporate-action conventions are not certified equivalent. No pass tolerance is assumed.',
            'checks': checks,
            'max_abs_close_difference_bps': max(abs(p['difference_bps']) for c in checks for p in c['closes']),
            'max_abs_return_difference_pp': max(abs(v['difference_pp']) for c in checks for v in c['returns'].values())}


def summarize_history(root):
    sessions = set()
    for path in Path(root).glob('*/*.json'):
        try:
            run = json.loads(path.read_text(encoding='utf-8'))
            day = date.fromisoformat(run['expected_session'])
            if (is_session(day) and run['result']['status'] == 'RESEARCH_ONLY'
                    and run['calculation_audit']['status'] == 'PASSED'):
                sessions.add(day)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    contiguous = 0
    if sessions:
        try:
            for day in reversed(trailing_sessions(max(sessions))):
                if day not in sessions:
                    break
                contiguous += 1
        except CalendarError:
            contiguous = 0
    return {'distinct_sessions': len(sessions), 'consecutive_sessions': contiguous,
            'latest_session': max(sessions).isoformat() if sessions else None,
            'pilot_target_sessions': 5,
            'status': 'MULTI_SESSION_SAMPLE_COLLECTED' if contiguous >= 5 else 'IN_PROGRESS',
            'note': 'Five sessions is a practical pilot target, not production approval or performance validation.'}


def archive_run(evidence, root):
    """Archive a safe evidence allowlist; repeated runs do not inflate sessions."""
    session = date.fromisoformat(evidence['expected_session'])
    stamp = datetime.fromisoformat(evidence['generated_utc'].replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('timezone-aware timestamp required')
    directory = Path(root) / session.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (stamp.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    allowed = ('expected_session', 'generated_utc', 'feed', 'result', 'calendar',
               'calculation_audit', 'cross_feed_verification', 'reference_verification', 'observations')
    payload = {key: evidence[key] for key in allowed if key in evidence}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if path.exists():
        if path.read_text(encoding='utf-8') != text:
            raise ValueError('conflicting run timestamp')
    else:
        atomic_write_text(path, text, overwrite=False)
    return summarize_history(root)
