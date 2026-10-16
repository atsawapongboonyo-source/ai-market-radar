"""Read-only, offline pipeline for rotation research.

Data acquisition and authoritative exchange calendar resolution are external.
No network, broker, alerts, or production route integration.
"""
from capital_rotation_data_quality import validate_snapshot
from capital_rotation_market_session import validate_completed_session
from capital_rotation_confirmation import confirm_rotation


def evaluate_rotation_snapshot(snapshot, *, expected_session, now_utc,
                               max_age_hours=36, max_skew_hours=12):
    """Return an auditable result, failing closed on any validation error.

    Important: a market-session check alone can accept weekend/holiday data,
    but the age check uses elapsed wall-clock hours. Callers must explicitly
    set max_age_hours for the verified market closure gap.
    """
    session = validate_completed_session(
        snapshot, expected_session=expected_session, now_utc=now_utc)
    if not session["ok"]:
        return {"status": "BLOCKED", "reason": session["reason"],
                "trade_signal": False, "candidates": []}
    quality = validate_snapshot(
        snapshot, now_utc=now_utc,
        max_age_hours=max_age_hours, max_skew_hours=max_skew_hours)
    if not quality["ok"]:
        return {"status": "BLOCKED", "reason": quality["reason"],
                "trade_signal": False, "candidates": []}
    analysis = confirm_rotation(quality["windows"], quality["freshness"])
    return {"status": "RESEARCH_ONLY", "session_date": session["session_date"],
            **analysis}
