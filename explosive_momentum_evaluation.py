"""Offline point-in-time momentum evaluation with explicit observation coverage.

No market access or trading. Metrics are computed only from externally supplied,
timestamped future outcomes, never inferred from alert strength.
"""
from datetime import datetime, timezone


def evaluate_replay(replay, outcomes, *, expected_symbols=None):
    """Score only labeled symbols; refuse precision claims on incomplete coverage.

    outcomes: iterable of {symbol, evaluated_after_utc, became_leader: bool}.
    Labels must be sourced independently and timestamped AFTER first observation.
    A complete eligible universe must be supplied explicitly by the caller.
    """
    if expected_symbols is None:
        return {"status": "BLOCKED", "reason": "UNIVERSE_COVERAGE_NOT_PROVEN"}
    expected = set(expected_symbols)
    if not expected or any(not isinstance(s, str) or not s for s in expected):
        return {"status": "BLOCKED", "reason": "INVALID_UNIVERSE"}
    events = replay.get("events", [])
    seen = {e["symbol"] for e in events}
    if not expected.issubset(seen):
        return {"status": "BLOCKED", "reason": "MISSING_SCREENED_SYMBOLS",
                "missing_count": len(expected - seen)}
    if seen - expected:
        return {"status": "BLOCKED", "reason": "UNEXPECTED_SCREENED_SYMBOLS"}
    first_observed = {}
    predicted = set()
    for event in events:
        symbol = event["symbol"]
        t = datetime.fromisoformat(event["observed_at_utc"])
        if t.tzinfo is None:
            return {"status": "BLOCKED", "reason": "NAIVE_EVENT_TIME"}
        first_observed[symbol] = min(t, first_observed.get(symbol, t))
        if event["state"] == "REVIEW":
            predicted.add(symbol)
    labels = {}
    for item in outcomes:
        symbol = item["symbol"]
        if symbol in labels or symbol not in expected or type(item["became_leader"]) is not bool:
            return {"status": "BLOCKED", "reason": "INVALID_OUTCOME_LABELS"}
        t = item["evaluated_after_utc"]
        if not isinstance(t, datetime) or t.tzinfo is None or t.astimezone(timezone.utc) <= first_observed[symbol].astimezone(timezone.utc):
            return {"status": "BLOCKED", "reason": "OUTCOME_NOT_AFTER_OBSERVATION"}
        labels[symbol] = item["became_leader"]
    if set(labels) != expected:
        return {"status": "BLOCKED", "reason": "INCOMPLETE_OUTCOME_LABELS",
                "missing_count": len(expected - set(labels))}
    tp = len(predicted & {s for s, v in labels.items() if v})
    fp = len(predicted) - tp
    fn = len({s for s, v in labels.items() if v} - predicted)
    tn = len(expected) - tp - fp - fn
    return {"status": "EVALUATED", "universe_size": len(expected),
            "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "true_negative": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "limitations": "REQUIRES_INDEPENDENT_POINT_IN_TIME_LABELS_AND_FULL_UNIVERSE"}
