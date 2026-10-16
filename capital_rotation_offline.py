"""Offline, read-only sector-rotation classifier. No network calls or trade actions."""
from math import isfinite

SECTORS = ("XLF", "XLV", "XLI", "XLE", "XLU", "XLP", "XLY", "XLC", "XLB", "XLRE", "XLK")
AI_PROXIES = ("SMH", "SOXX")


def _valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def classify_rotation(returns_5d, fresh_symbols, *, benchmark="SPY"):
    """Classify relative rotation from supplied 5-day percent returns.

    No inference of actual capital flows. Missing/stale benchmark or AI proxy
    fails closed; output is research-only and never a buy recommendation.
    """
    required = (benchmark,) + AI_PROXIES
    if any(symbol not in fresh_symbols or not _valid_number(returns_5d.get(symbol)) for symbol in required):
        return {"regime": "INSUFFICIENT_DATA", "candidates": [], "trade_signal": False}
    market = float(returns_5d[benchmark])
    ai = sum(float(returns_5d[symbol]) for symbol in AI_PROXIES) / len(AI_PROXIES)
    candidates = []
    valid_sectors = 0
    for symbol in SECTORS:
        value = returns_5d.get(symbol)
        if symbol not in fresh_symbols or not _valid_number(value):
            continue
        valid_sectors += 1
        relative = float(value) - market
        if relative > 0 and float(value) > 0:
            candidates.append({"symbol": symbol, "return_5d_pct": float(value), "relative_to_spy_pct": round(relative, 3)})
    candidates.sort(key=lambda item: (-item["relative_to_spy_pct"], item["symbol"]))
    if valid_sectors < 6:
        regime = "INSUFFICIENT_DATA"
        candidates = []
    elif market < 0 and not candidates:
        regime = "BROAD_RISK_OFF"
    elif ai >= market:
        regime = "AI_LEADING_OR_MIXED"
    elif ai < 0 and candidates:
        regime = "POSSIBLE_ROTATION"
    else:
        regime = "MIXED"
    return {
        "regime": regime,
        "benchmark_5d_pct": market,
        "ai_proxy_avg_5d_pct": round(ai, 3),
        "candidates": candidates,
        "trade_signal": False,
        "note": "Relative price strength is not evidence of actual capital transfers.",
    }
