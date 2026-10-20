"""Run an opt-in read-only Capital Rotation report from Alpaca daily bars.

Requires ALPACA_DATA_KEY_ID and ALPACA_DATA_SECRET_KEY in the local environment.
Usage: python capital_rotation_alpaca_report.py 2026-10-16
Omit the session date to use the pinned NYSE calendar (2026-2028 only).
No trading endpoints, automatic schedules, secrets output, or production writes.
"""
import argparse
from datetime import date, datetime, timezone
import json
import sys
from pathlib import Path
from capital_rotation_alpaca import MarketDataError, fetch_from_environment
from capital_rotation_report import build_report
from capital_rotation_html import save_rotation_html
from capital_rotation_calendar import (CalendarError, last_completed_session,
                                      calendar_age_limit, SOURCE, REVIEWED)
from capital_rotation_audit import audit_snapshot, compare_feeds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("completed_session", type=date.fromisoformat, nargs='?')
    parser.add_argument("--feed", choices=("iex", "sip"), default="iex")
    parser.add_argument("--html", help="Optional local static HTML output path")
    parser.add_argument("--max-age-hours", type=float)
    parser.add_argument('--audit-json', type=Path, help='Local price and calculation evidence; no credentials')
    parser.add_argument('--verify-sip', action='store_true', help='One extra read-only historical SIP request to compare IEX closes')
    args = parser.parse_args(argv)
    if args.max_age_hours is not None and not 0 < args.max_age_hours <= 120:
        parser.error("max-age-hours must be > 0 and <= 120")
    if args.verify_sip and args.feed != 'iex':
        parser.error('verify-sip requires primary feed iex')
    now = datetime.now(timezone.utc)
    completed = args.completed_session
    snapshot = None
    try:
        latest = last_completed_session(now)
        if completed is not None and completed != latest:
            raise CalendarError('NOT_LATEST_COMPLETED_SESSION')
        completed = latest
        max_age = args.max_age_hours if args.max_age_hours is not None else calendar_age_limit(completed, now)
        snapshot = fetch_from_environment(
            expected_session=completed, feed=args.feed
        )
    except (MarketDataError, CalendarError) as exc:
        report = {"expected_session": completed.isoformat() if completed else None,
                  "generated_utc": now.isoformat(),
                  "feed": args.feed,
                  "result": {"status": "BLOCKED", "reason": str(exc),
                             "trade_signal": False, "candidates": []}}
        if args.html:
            save_rotation_html(report, args.html)
        if args.audit_json:
            args.audit_json.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        return 2
    report = build_report(snapshot, expected_session=completed,
                          now_utc=now, max_age_hours=max_age)
    report["feed"] = args.feed
    report['calendar'] = {'source': SOURCE, 'reviewed': REVIEWED,
                          'coverage': '2026-2028 scheduled core sessions; unscheduled closures not detected',
                          'readiness_buffer_minutes': 20, 'max_age_hours': max_age}
    report['calculation_audit'] = audit_snapshot(snapshot, expected_session=completed)
    if report['calculation_audit']['status'] != 'PASSED':
        report['result'] = {'status': 'BLOCKED', 'reason': 'CALCULATION_AUDIT_FAILED',
                            'trade_signal': False, 'candidates': []}
    report['cross_feed_verification'] = {'status': 'NOT_RUN'}
    if args.verify_sip:
        try:
            reference = fetch_from_environment(expected_session=completed, feed='sip')
            reference_audit = audit_snapshot(reference, expected_session=completed)
            if reference_audit['status'] != 'PASSED':
                report['cross_feed_verification'] = {'status': 'BLOCKED', 'reason': 'REFERENCE_AUDIT_FAILED'}
            else:
                report['cross_feed_verification'] = compare_feeds(snapshot, reference)
        except MarketDataError as exc:
            report['cross_feed_verification'] = {'status': 'BLOCKED', 'reason': str(exc)}
    if args.audit_json:
        evidence = dict(report, observations=snapshot['_observations'])
        args.audit_json.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding='utf-8')
    if args.html:
        save_rotation_html(report, args.html)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"]["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
