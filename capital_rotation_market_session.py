"""Exchange-session freshness checks for offline research.

The caller must supply the last *completed* US equity session date from a
verified exchange calendar. No holiday rules are guessed here.
"""
from datetime import date, datetime, timezone


def validate_completed_session(snapshot, *, expected_session, now_utc, maximum_lag_days=0):
    """Require all input windows to reference the same completed session.

    Snapshot format: {window: {symbol: {return_pct, asof_utc, session_date}}}
    Dates are ISO YYYY-MM-DD; this deliberately checks session identity, not
    elapsed wall-clock hours (which would mislabel weekends/holidays as stale).
    """
    fail = {"ok": False, "reason": "INVALID_SESSION"}
    if not isinstance(expected_session, date) or isinstance(expected_session, datetime):
        return dict(fail, reason="MISSING_EXCHANGE_CALENDAR")
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        return dict(fail, reason="INVALID_NOW")
    if not isinstance(maximum_lag_days, int) or isinstance(maximum_lag_days, bool) or maximum_lag_days != 0:
        return dict(fail, reason="UNSUPPORTED_LAG")
    if expected_session > now_utc.astimezone(timezone.utc).date():
        return dict(fail, reason="FUTURE_SESSION")
    if not isinstance(snapshot, dict):
        return fail
    for window in ("5d", "20d"):
        rows = snapshot.get(window)
        if not isinstance(rows, dict) or not rows:
            return dict(fail, reason="MISSING_WINDOW")
        for symbol, row in rows.items():
            if not isinstance(row, dict) or not isinstance(row.get("session_date"), str):
                return dict(fail, reason="MISSING_SESSION_DATE")
            try:
                session = date.fromisoformat(row["session_date"])
            except ValueError:
                return dict(fail, reason="INVALID_SESSION_DATE")
            if session != expected_session:
                return dict(fail, reason="MISMATCHED_OR_STALE_SESSION")
    return {"ok": True, "reason": "VALID_COMPLETED_SESSION",
            "session_date": expected_session.isoformat(),
            "note": "Expected session must come from an authoritative exchange calendar."}
