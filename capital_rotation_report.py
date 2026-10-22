"""Local read-only Capital Rotation report from an explicitly supplied JSON snapshot.

Usage: python capital_rotation_report.py snapshot.json 2026-10-16
The date MUST be the independently verified last completed US equity session.
Never fetches quotes, sends orders, or touches the production scanner.
"""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from capital_rotation_pipeline import evaluate_rotation_snapshot


def build_report(snapshot, *, expected_session, now_utc, max_age_hours=36):
    result = evaluate_rotation_snapshot(
        snapshot, expected_session=expected_session, now_utc=now_utc,
        max_age_hours=max_age_hours
    )
    return {
        "disclaimer": "Relative price performance proxy, NOT measured fund flows or a trade signal.",
        "generated_utc": now_utc.isoformat(),
        "expected_session": expected_session.isoformat(),
        "result": result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Local JSON snapshot; no network")
    parser.add_argument("completed_session", type=date.fromisoformat,
                        help="Verified US exchange session YYYY-MM-DD")
    parser.add_argument("--max-age-hours", type=float, default=36)
    args = parser.parse_args(argv)
    if not 0 < args.max_age_hours <= 120:
        parser.error("--max-age-hours must be > 0 and <= 120")
    with args.snapshot.open(encoding="utf-8") as handle:
        snapshot = json.load(handle)
    report = build_report(
        snapshot, expected_session=args.completed_session,
        now_utc=datetime.now(timezone.utc), max_age_hours=args.max_age_hours
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["result"]["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
