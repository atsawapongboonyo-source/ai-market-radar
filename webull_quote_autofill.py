"""Offline-only quote data validation for proposed Radar autofill.

No credentials, networking, broker actions, or production integration.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def normalize_quote(snapshot, symbol, now_utc, max_age_seconds=120):
    if not isinstance(snapshot, dict) or snapshot.get("symbol") != symbol:
        raise ValueError("symbol mismatch")
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise ValueError("timezone-aware now required")
    try:
        timestamp = snapshot["last_trade_time"]
        if isinstance(timestamp, bool):
            raise ValueError("invalid timestamp")
        observed = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
        price = Decimal(str(snapshot["price"]))
        close = Decimal(str(snapshot["pre_close"]))
    except (KeyError, ValueError, TypeError, OverflowError, InvalidOperation, OSError):
        raise ValueError("invalid quote") from None
    if not price.is_finite() or not close.is_finite() or price <= 0 or close <= 0:
        raise ValueError("invalid price")
    age = (now_utc.astimezone(timezone.utc) - observed).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise ValueError("stale quote")
    return {
        "symbol": symbol,
        "price": str(price),
        "previous_close": str(close),
        "asof_utc": observed.isoformat(),
        "source": "WEBULL_OPENAPI_UNVERIFIED",
        "session": "UNVERIFIED",
        "autofill_eligible": False,
    }
