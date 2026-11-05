"""Offline intraday explosive momentum detector; no network, storage or orders.

Requires completed 1-minute bars with UTC timestamps and *same-feed,
same-session* point-in-time baseline volumes. Feed completeness is a caller
contract; IEX volume is NOT consolidated market volume.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class IntradayEvent:
    symbol: str
    state: str
    gain_pct: float
    acceleration_5m_pct: float
    acceleration_15m_pct: float
    relative_volume: float
    spread_bps: float
    reasons: tuple[str, ...]


def detect_intraday(symbol, bars, baseline_same_clock_volumes, *,
                    observed_at_utc, session_open_price, bid, ask,
                    feed, session, min_gain_pct=10, max_gain_pct=30,
                    min_relative_volume=3, max_spread_bps=100,
                    min_dollar_turnover=1_000_000, max_age_seconds=120):
    """Review 16 completed 1-minute bars; no prediction or order decision.

    Bars: [{timestamp_utc, close, volume}, ...], chronological contiguous UTC
    minutes. Baseline: >=10 strictly positive prior-session 15-minute volume
    totals for the same session and clock time, not a full-day average.
    """
    def blocked(reason):
        return IntradayEvent(str(symbol), "BLOCKED", 0, 0, 0, 0, 0, (reason,))
    if not isinstance(symbol, str) or not symbol or session not in ("REGULAR", "PREMARKET", "AFTERHOURS"):
        return blocked("INVALID_CONTEXT")
    if feed not in ("SIP", "IEX") or not isinstance(observed_at_utc, datetime) or observed_at_utc.tzinfo is None:
        return blocked("INVALID_CONTEXT")
    if len(bars) < 16 or len(baseline_same_clock_volumes) < 10:
        return blocked("INSUFFICIENT_HISTORY")
    try:
        prices = []
        volumes = []
        times = []
        for row in bars[-16:]:
            t = datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
            if t.tzinfo is None:
                raise ValueError()
            times.append(t.astimezone(timezone.utc))
            p, v = float(row["close"]), float(row["volume"])
            if not isfinite(p) or p <= 0 or not isfinite(v) or v < 0:
                raise ValueError()
            prices.append(p)
            volumes.append(v)
        if any((b-a).total_seconds() != 60 for a, b in zip(times, times[1:])):
            return blocked("NONCONTIGUOUS_BARS")
        age = (observed_at_utc.astimezone(timezone.utc) - times[-1]).total_seconds()
        if age < 0 or age > max_age_seconds:
            return blocked("STALE_OR_FUTURE_DATA")
        open_price, bid, ask = float(session_open_price), float(bid), float(ask)
        if any(not isfinite(v) or v <= 0 for v in (open_price, bid, ask)) or ask < bid:
            return blocked("INVALID_QUOTES")
        baseline = [float(v) for v in baseline_same_clock_volumes]
        if any(not isfinite(v) or v <= 0 for v in baseline):
            return blocked("INVALID_BASELINE")
        # Baseline and recent volumes are both 15-minute totals.
        rvol = sum(volumes[1:]) / median(baseline)
        gain = (prices[-1] / open_price - 1) * 100
        accel5 = (prices[-1] / prices[-6] - 1) * 100
        accel15 = (prices[-1] / prices[0] - 1) * 100
        spread = (ask-bid) / ((ask+bid)/2) * 10000
        turnover = sum(p*v for p, v in zip(prices[1:], volumes[1:]))
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError):
        return blocked("INVALID_DATA")
    reasons = []
    if gain < min_gain_pct:
        reasons.append("BELOW_GAIN_WINDOW")
    if gain > max_gain_pct:
        reasons.append("OVEREXTENDED")
    if rvol < min_relative_volume:
        reasons.append("LOW_RELATIVE_VOLUME")
    if spread > max_spread_bps:
        reasons.append("WIDE_SPREAD")
    if turnover < min_dollar_turnover:
        reasons.append("LOW_TURNOVER")
    if accel5 <= 0 or accel15 <= 0:
        reasons.append("MOMENTUM_NOT_ACCELERATING")
    if feed == "IEX":
        reasons.append("PARTIAL_MARKET_FEED")
    state = "REVIEW" if not reasons else "WATCH"
    if gain > max_gain_pct:
        state = "OVEREXTENDED"
    return IntradayEvent(symbol, state, round(gain, 3), round(accel5, 3),
                         round(accel15, 3), round(rvol, 3), round(spread, 2),
                         tuple(reasons))
