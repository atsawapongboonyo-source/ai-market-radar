"""Local IEX-only automation. All provider access is the read-only bars adapter.

Credentials exist only in this process environment, supplied by a DPAPI wrapper.
Scheduled checks run every 15 minutes; exchange calendar determines data due.
No scheduler installation, orders, production routes, or credentials in output.
"""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import os

from capital_rotation_alpaca import (MarketDataError, SYMBOLS, fetch_from_environment,
                                    _daily_close_snapshot)
from capital_rotation_audit import audit_snapshot
from capital_rotation_calendar import (CalendarError, last_completed_session,
    trailing_sessions, session_close, is_session, ny_timezone, calendar_age_limit,
    SOURCE, REVIEWED)
from capital_rotation_report import build_report
from capital_rotation_html import save_rotation_html
from capital_rotation_storage import atomic_write_text

SAFE_ERRORS = {'MISSING_CREDENTIALS', 'CREDENTIALS_UNAVAILABLE', 'AUTHENTICATION_FAILED',
    'FEED_ACCESS_DENIED', 'RATE_LIMITED', 'PROVIDER_UNAVAILABLE', 'RESPONSE_TOO_LARGE',
    'INVALID_OR_PAGINATED_RESPONSE', 'MISSING_BARS', 'MISSING_SYMBOL_DATA', 'INVALID_BAR',
    'DUPLICATE_SESSION', 'INSUFFICIENT_COMPLETED_SESSIONS', 'MISALIGNED_SYMBOL_SESSIONS',
    'MISSING_EXCHANGE_SESSIONS', 'CALENDAR_UNAVAILABLE', 'TIMEZONE_DATA_UNAVAILABLE',
    'UNSUPPORTED_CALENDAR_DATE', 'UNSUPPORTED_CLOSURE_GAP', 'NOT_EXCHANGE_SESSION',
    'CALCULATION_AUDIT_FAILED', 'DATA_QUALITY_FAILED', 'DATA_WRITE_FAILED', 'INTERNAL_ERROR',
    'CATCH_UP_LIMIT_EXCEEDED', 'WRAPPER_FAILED'}


def safe_code(value):
    return value if value in SAFE_ERRORS else 'INTERNAL_ERROR'


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def next_market_due(now):
    day = now.astimezone(ny_timezone()).date()
    for _ in range(12):
        if is_session(day):
            ready = session_close(day) + timedelta(minutes=20)
            if ready > now:
                return ready
        day += timedelta(days=1)
    raise CalendarError('NO_COMPLETED_SESSION')


def valid_saved(evidence, session):
    try:
        if (evidence.get('feed') != 'iex' or evidence['expected_session'] != session.isoformat()
                or evidence['result']['status'] != 'RESEARCH_ONLY'):
            return False
        observations = evidence['observations']
        if set(observations) != set(SYMBOLS) or any(len(rows) != 21 for rows in observations.values()):
            return False
        payload = {'bars': {s: [{'t': r['bar_timestamp_utc'], 'c': r['close']} for r in rows]
                            for s, rows in observations.items()}}
        snapshot = _daily_close_snapshot(payload, expected_session=session)
        recomputed = audit_snapshot(snapshot, expected_session=session)
        if recomputed['status'] != 'PASSED' or evidence.get('calculation_audit') != recomputed:
            return False
        # Recompute classification; a forged PASSED label does not bypass checks.
        replay = build_report(snapshot, expected_session=session,
            now_utc=session_close(session) + timedelta(minutes=20), max_age_hours=36)
        return replay['result'] == evidence['result']
    except (KeyError, TypeError, ValueError, MarketDataError):
        return False


@contextmanager
def run_lock(root):
    """OS-released lock survives crashes without leaving a stale lock directory."""
    import msvcrt
    path = Path(root) / 'run.lock'
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def run_once(root, *, now=None, fetcher=fetch_from_environment, forced_error=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('aware time required')
    previous = read_json(root / 'health.json')
    scheduler = read_json(root / 'scheduler.json')
    health = {'status': 'CHECKING', 'error_code': None,
              'last_check_utc': now.isoformat(),
              'last_success_utc': previous.get('last_success_utc'),
              'last_success_session': previous.get('last_success_session'),
              'task_name': scheduler.get('task_name', 'AI Market Radar Capital Rotation Local'),
              'next_check_utc': scheduler.get('next_check_utc'),
              'credential_storage': 'DPAPI_CURRENT_USER', 'feed': 'iex',
              'downloaded_sessions': [], 'latest_session': None,
              'next_market_due_utc': None}
    report = {'expected_session': None, 'generated_utc': now.isoformat(), 'feed': 'iex',
              'result': {'status': 'BLOCKED', 'reason': 'NOT_EVALUATED',
                         'candidates': [], 'trade_signal': False}}
    try:
        latest = last_completed_session(now)
        health['latest_session'] = latest.isoformat()
        health['next_market_due_utc'] = next_market_due(now).isoformat()
        report['expected_session'] = latest.isoformat()
        if forced_error:
            raise MarketDataError(safe_code(forced_error))
        # First install captures latest only. Later runs fill bounded missing days.
        valid = {}
        supported = trailing_sessions(latest)
        if previous.get('last_success_session'):
            previous_session = date.fromisoformat(previous['last_success_session'])
            if previous_session < supported[0]:
                raise MarketDataError('CATCH_UP_LIMIT_EXCEEDED')
        for day in supported:
            saved = read_json(root / 'daily' / (day.isoformat() + '.json'))
            if valid_saved(saved, day):
                valid[day] = saved
        first = min(valid) if valid else latest
        due = [d for d in supported if d >= first and d not in valid]
        for day in due:
            snapshot = fetcher(expected_session=day, feed='iex')
            audit = audit_snapshot(snapshot, expected_session=day)
            if audit['status'] != 'PASSED':
                raise MarketDataError('CALCULATION_AUDIT_FAILED')
            evaluation = now if day == latest else session_close(day) + timedelta(minutes=20)
            age_limit = calendar_age_limit(latest, now) if day == latest else 36
            daily = build_report(snapshot, expected_session=day, now_utc=evaluation,
                                 max_age_hours=age_limit)
            if daily['result']['status'] != 'RESEARCH_ONLY':
                raise MarketDataError('DATA_QUALITY_FAILED')
            daily.update(generated_utc=now.isoformat(), evaluation_utc=evaluation.isoformat(),
                historical_catch_up=day != latest, feed='iex', calculation_audit=audit,
                observations=snapshot['_observations'], calendar={'source': SOURCE,
                    'reviewed': REVIEWED, 'coverage': '2026-2028 scheduled core sessions only'},
                cross_feed_verification={'status': 'NOT_RUN'})
            write_json(root / 'daily' / (day.isoformat() + '.json'), daily)
            valid[day] = daily
            health['downloaded_sessions'].append(day.isoformat())
            health['last_success_utc'] = now.isoformat()
            health['last_success_session'] = day.isoformat()
        report = dict(valid[latest])
        # Correct freshness is checked even when no data download was needed.
        calendar_age_limit(latest, now)
        if not health['last_success_utc']:
            health['last_success_utc'] = report['generated_utc']
            health['last_success_session'] = latest.isoformat()
        health['status'] = 'OK' if due else 'UP_TO_DATE'
        health['symbols'] = len(SYMBOLS)
        health['sessions_per_symbol'] = 21
        health['stored_sessions'] = len(valid)
    except (MarketDataError, CalendarError) as exc:
        health.update(status='BLOCKED', error_code=safe_code(str(exc)))
    except OSError:
        health.update(status='BLOCKED', error_code='DATA_WRITE_FAILED')
    except Exception:
        # No exception text, provider bodies, HTTP headers or process environment.
        health.update(status='BLOCKED', error_code='INTERNAL_ERROR')
    if health['status'] == 'BLOCKED':
        report['result'] = {'status': 'BLOCKED', 'reason': health['error_code'],
                            'trade_signal': False, 'candidates': []}
    report['automation_health'] = health
    write_json(root / 'health.json', health)
    save_rotation_html(report, root / 'rotation-dashboard.html')
    return health


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--error', choices=sorted(SAFE_ERRORS))
    args = parser.parse_args(argv)
    args.root.mkdir(parents=True, exist_ok=True)
    try:
        with run_lock(args.root) as acquired:
            if not acquired:
                return 0
            health = run_once(args.root, forced_error=args.error)
        print(json.dumps({'status': health['status'], 'error_code': health['error_code']}))
        return 0 if health['status'] in ('OK', 'UP_TO_DATE') else 2
    except Exception:
        print('{"status":"BLOCKED","error_code":"DATA_WRITE_FAILED"}')
        return 2
    finally:
        os.environ.pop('ALPACA_DATA_KEY_ID', None)
        os.environ.pop('ALPACA_DATA_SECRET_KEY', None)


if __name__ == '__main__':
    raise SystemExit(main())
