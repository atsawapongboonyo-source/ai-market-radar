"""Pure, offline freshness classification for future Stock Radar V2 UI.

No network calls, trading actions, or Production route changes.
"""
from datetime import datetime, timezone
from math import isfinite


def _utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def classify_freshness(observed_at_utc, now_utc, *, max_age_seconds=180, cached=False):
    """Return an explicit label without treating cache age as quote age.

    FRESH requires a valid timestamp at or before now and a threshold pass.
    A future bar, missing timestamp or invalid threshold is UNKNOWN.
    An EOD bar should be labeled EOD separately, not passed off as live.
    """
    observed, now = _utc(observed_at_utc), _utc(now_utc)
    if not observed or not now or isinstance(max_age_seconds, bool):
        return {"freshness": "UNKNOWN", "age_seconds": None, "cached": bool(cached)}
    try:
        threshold = float(max_age_seconds)
    except (TypeError, ValueError, OverflowError):
        threshold = float("nan")
    if not isfinite(threshold) or threshold < 0:
        return {"freshness": "UNKNOWN", "age_seconds": None, "cached": bool(cached)}
    age = (now - observed).total_seconds()
    if age < 0:
        return {"freshness": "UNKNOWN", "age_seconds": None, "cached": bool(cached)}
    return {
        "freshness": "FRESH" if age <= threshold else "STALE",
        "age_seconds": int(age),
        "cached": bool(cached),
    }
