"""Offline, research-only explosive momentum event detector.

Input bars must be chronological, completed, regular-session, same adjustment
and feed. This module makes no network calls and never places orders.
"""
from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class MomentumEvent:
    symbol: str
    state: str
    return_pct: float
    relative_volume: float
    dollar_volume: float
    reasons: tuple[str, ...]


def detect(symbol, bars, *, min_price=1.0, min_dollar_volume=1_000_000,
           min_relative_volume=3.0, min_gain_pct=10.0, max_gain_pct=30.0):
    """Classify last completed bar against 20 PRIOR completed sessions.

    A flag is an anomaly for review, not a prediction, trading signal or
    evidence that a stock was detected before any public leaderboard.
    """
    if not isinstance(symbol, str) or not symbol or len(bars) < 21:
        return MomentumEvent(str(symbol), "BLOCKED", 0.0, 0.0, 0.0, ("INSUFFICIENT_HISTORY",))
    sample = bars[-21:]
    try:
        sessions = [row["session"] for row in sample]
        if sessions != sorted(set(sessions)):
            raise ValueError("duplicate or unordered sessions")
        for row in sample:
            for key in ("close", "volume"):
                v = float(row[key])
                if not isfinite(v) or v <= 0:
                    raise ValueError("invalid price or volume")
        previous = float(sample[-2]["close"])
        latest = float(sample[-1]["close"])
        volume = float(sample[-1]["volume"])
        prior_volume = median(float(row["volume"]) for row in sample[:-1])
    except (KeyError, TypeError, ValueError, OverflowError):
        return MomentumEvent(symbol, "BLOCKED", 0.0, 0.0, 0.0, ("INVALID_BARS",))
    gain = (latest / previous - 1) * 100
    rvol = volume / prior_volume
    dollars = latest * volume
    reasons = []
    if latest < min_price:
        reasons.append("LOW_PRICE")
    if dollars < min_dollar_volume:
        reasons.append("LOW_DOLLAR_LIQUIDITY")
    if rvol < min_relative_volume:
        reasons.append("VOLUME_NOT_UNUSUAL")
    if gain < min_gain_pct:
        reasons.append("BELOW_GAIN_WINDOW")
    if gain > max_gain_pct:
        reasons.append("ALREADY_ABOVE_GAIN_WINDOW")
    state = "FLAGGED_FOR_REVIEW" if not reasons else "NO_FLAG"
    return MomentumEvent(symbol, state, round(gain, 3), round(rvol, 3),
                         round(dollars, 2), tuple(reasons))
