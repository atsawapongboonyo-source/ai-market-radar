"""Point-in-time offline replay for the intraday research detector.

Caller supplies full chronological snapshots (including non-winners) with
as-of quote and same-clock historical baselines. No data fetching, trades,
or survivorship-adjusted performance claims.
"""
from collections import Counter
from datetime import datetime, timezone
from explosive_momentum_intraday import detect_intraday


def replay_snapshots(snapshots):
    """Return auditable alert counts and first alert times, without look-ahead.

    snapshots: iterable of {symbol, observed_at_utc, bars, baseline,
    session_open_price, bid, ask, feed, session}. Timestamps are UTC
    datetimes; each snapshot independently evaluated using only supplied
    data known at that time. This function intentionally does not label
    outcomes as true/false positives without separately sourced future data.
    """
    events = []
    for row in snapshots:
        observed = row["observed_at_utc"]
        if not isinstance(observed, datetime) or observed.tzinfo is None:
            raise ValueError("OBSERVATION_TIME_REQUIRED")
        event = detect_intraday(
            row["symbol"], row["bars"], row["baseline"],
            observed_at_utc=observed,
            session_open_price=row["session_open_price"],
            bid=row["bid"], ask=row["ask"],
            feed=row["feed"], session=row["session"])
        events.append({"symbol":row["symbol"], "observed_at_utc":observed.astimezone(timezone.utc).isoformat(),
                       "state":event.state, "reasons":list(event.reasons),
                       "gain_pct":event.gain_pct, "relative_volume":event.relative_volume})
    events.sort(key=lambda e: (e["observed_at_utc"], e["symbol"]))
    counts = Counter(e["state"] for e in events)
    first_review = {}
    for event in events:
        if event["state"] == "REVIEW":
            first_review.setdefault(event["symbol"], event["observed_at_utc"])
    return {"schema_version": 1, "snapshots": len(events),
            "states": {s: counts[s] for s in ("REVIEW", "WATCH", "OVEREXTENDED", "BLOCKED")},
            "first_review_utc": first_review, "events": events,
            "limitations": "NO_OUTCOME_LABELS_NO_PRECISION_CLAIM_NO_MARKET_WIDE_COVERAGE"}
