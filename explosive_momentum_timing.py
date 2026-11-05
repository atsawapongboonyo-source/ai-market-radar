"""Validate time alignment of one-minute bars and quote snapshots.

Offline-only checks. No network calls or trading actions.
"""
from datetime import datetime, timezone


def parse_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def validate_snapshot_timing(snapshot, observed_at_utc):
    if observed_at_utc.tzinfo is None:
        return "INVALID_OBSERVATION_TIME"
    try:
        bars = snapshot["bars"]
        quote = snapshot["latest_quote"]
        if len(bars) < 16:
            return "INSUFFICIENT_BARS"
        timestamps = [parse_time(row["timestamp_utc"]) for row in bars[-16:]]
        quote_time = parse_time(quote["timestamp_utc"])
        observed = observed_at_utc.astimezone(timezone.utc)
        if any((b-a).total_seconds() != 60 for a,b in zip(timestamps,timestamps[1:])):
            return "BAR_GAP"
        if not (0 <= (observed-timestamps[-1]).total_seconds() <= 120):
            return "STALE_BAR"
        if not (0 <= (observed-quote_time).total_seconds() <= 120):
            return "STALE_QUOTE"
        if quote_time < timestamps[-1]:
            return "QUOTE_BEFORE_BAR"
        return "READY_FOR_RESEARCH"
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return "INVALID_SNAPSHOT"
