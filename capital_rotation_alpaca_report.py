"""Run an opt-in read-only Capital Rotation report from Alpaca daily bars.

Requires ALPACA_DATA_KEY_ID and ALPACA_DATA_SECRET_KEY in the local environment.
Usage: python capital_rotation_alpaca_report.py 2026-10-16
The session date MUST be verified from an exchange calendar by the operator.
No trading endpoints, automatic schedules, secrets output, or production writes.
"""
import argparse
from datetime import date, datetime, timezone
import json
import sys
from capital_rotation_alpaca import MarketDataError, fetch_from_environment
from capital_rotation_report import build_report
from capital_rotation_html import save_rotation_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("completed_session", type=date.fromisoformat)
    parser.add_argument("--feed", choices=("iex", "sip"), default="iex")
    parser.add_argument("--html", help="Optional local static HTML output path")
    parser.add_argument("--max-age-hours", type=float, default=36)
    args = parser.parse_args(argv)
    if not 0 < args.max_age_hours <= 120:
        parser.error("max-age-hours must be > 0 and <= 120")
    try:
        snapshot = fetch_from_environment(
            expected_session=args.completed_session, feed=args.feed
        )
    except MarketDataError as exc:
        report = {"expected_session": args.completed_session.isoformat(),
                  "generated_utc": datetime.now(timezone.utc).isoformat(),
                  "feed": args.feed,
                  "result": {"status": "BLOCKED", "reason": str(exc),
                             "trade_signal": False, "candidates": []}}
        if args.html:
            save_rotation_html(report, args.html)
        print(json.dumps(report))
        return 2
    report = build_report(snapshot, expected_session=args.completed_session,
                          now_utc=datetime.now(timezone.utc),
                          max_age_hours=args.max_age_hours)
    report["feed"] = args.feed
    if args.html:
        save_rotation_html(report, args.html)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"]["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
