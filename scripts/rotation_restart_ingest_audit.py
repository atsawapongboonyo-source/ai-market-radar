"""Read-only Render log audit for restart/ingest continuity.

Accepts exported Render application log JSON on stdin or via --input.
Never contacts Render, never modifies a service, and never logs credentials.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

TERM = re.compile(r"Handling signal: term")
INGEST = re.compile(r'"POST /api/rotation/ingest HTTP/1\.1" (\d{3})')


def audit(logs):
    events = []
    for row in logs:
        msg = row.get("message", "")
        timestamp = row.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
            dt = dt.astimezone(timezone.utc)
        except (ValueError, AttributeError, TypeError):
            continue
        if TERM.search(msg):
            kind, status = "term", None
        elif (match := INGEST.search(msg)):
            kind, status = "ingest", int(match.group(1))
        elif '"event": "ROTATION_STORAGE_VERIFICATION"' in msg:
            kind, status = "storage", None
        else:
            continue
        events.append((dt, kind, status))
    events.sort()
    terms = [t for t, kind, _ in events if kind == "term"]
    ingests = [(t, status) for t, kind, status in events if kind == "ingest"]
    gaps = [round((b - a).total_seconds()) for a, b in zip(terms, terms[1:])]
    return {
        "termination_count": len(terms),
        "termination_intervals_seconds": gaps,
        "ingest_count": len(ingests),
        "ingest_http_200_count": sum(status == 200 for _, status in ingests),
        "ingest_other_status_count": sum(status != 200 for _, status in ingests),
        "storage_verification_log_count": sum(kind == "storage" for _, kind, _ in events),
        "caveat": "Log samples cannot prove scheduler completeness, platform restart cause or successful persistence of every ingest.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Exported Render JSON file; default stdin")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") if args.input else sys.stdin as stream:
        payload = json.load(stream)
    print(json.dumps(audit(payload["logs"] if isinstance(payload, dict) else payload), indent=2))


if __name__ == "__main__":
    main()
