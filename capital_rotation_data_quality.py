"""Offline input validation for sector rotation. No market-data downloads."""
from datetime import datetime, timezone
from math import isfinite
from capital_rotation_offline import SECTORS, AI_PROXIES

REQUIRED = ("SPY",) + AI_PROXIES
WINDOWS = ("5d", "20d")


def validate_snapshot(snapshot, *, now_utc, max_age_hours=36, max_skew_hours=12):
    """Return validated returns/freshness or fail closed.

    snapshot format: {window: {symbol: {"return_pct": number, "asof_utc": ISO8601}}}
    Upstream must provide already computed window returns; timestamps must
    represent the same close/observation date for cross-sectional comparisons.
    """
    empty = {"ok": False, "reason": "INVALID_DATA", "windows": {}, "freshness": {}}
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        return dict(empty, reason="INVALID_NOW")
    if not isinstance(snapshot, dict) or not isinstance(max_age_hours, (int, float)) or max_age_hours <= 0 or not isinstance(max_skew_hours, (int, float)) or max_skew_hours < 0:
        return empty
    normalized = {}
    freshness = {}
    for window in WINDOWS:
        rows = snapshot.get(window)
        if not isinstance(rows, dict):
            return dict(empty, reason="MISSING_WINDOW")
        normalized[window], freshness[window] = {}, set()
        observations = []
        for symbol in REQUIRED + SECTORS:
            row = rows.get(symbol)
            if not isinstance(row, dict):
                continue
            value, stamp = row.get("return_pct"), row.get("asof_utc")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not isinstance(stamp, str):
                continue
            try:
                observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                continue
            if observed.tzinfo is None:
                continue
            age_hours = (now_utc.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 3600
            if not 0 <= age_hours <= max_age_hours:
                continue
            normalized[window][symbol] = float(value)
            freshness[window].add(symbol)
            observations.append(observed.astimezone(timezone.utc))
        if any(symbol not in freshness[window] for symbol in REQUIRED):
            return dict(empty, reason="MISSING_OR_STALE_REQUIRED")
        if sum(symbol in freshness[window] for symbol in SECTORS) < 6:
            return dict(empty, reason="INSUFFICIENT_SECTORS")
        # Remove sector observations that differ from the benchmark close.
        benchmark_observed = datetime.fromisoformat(rows["SPY"]["asof_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
        for symbol in tuple(freshness[window]):
            stamp = datetime.fromisoformat(rows[symbol]["asof_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if abs((stamp - benchmark_observed).total_seconds()) > max_skew_hours * 3600:
                freshness[window].remove(symbol)
                normalized[window].pop(symbol, None)
        if any(symbol not in freshness[window] for symbol in REQUIRED):
            return dict(empty, reason="SKEWED_REQUIRED")
        if sum(symbol in freshness[window] for symbol in SECTORS) < 6:
            return dict(empty, reason="SKEWED_SECTORS")
    return {"ok": True, "reason": "VALID", "windows": normalized, "freshness": freshness}
