"""Offline multi-window confirmation; never places orders or fetches market data."""
from math import isfinite
from capital_rotation_offline import AI_PROXIES, SECTORS


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def confirm_rotation(windows, freshness, *, benchmark="SPY"):
    """Require positive absolute and benchmark-relative sector returns in 5d AND 20d.

    windows: {"5d": {symbol: percent_return}, "20d": {...}}
    freshness: {"5d": {symbols}, "20d": {symbols}} from upstream validator.
    Caller must verify timestamp freshness and source integrity.
    """
    for window in ("5d", "20d"):
        data = windows.get(window, {})
        fresh = freshness.get(window, set())
        if any(symbol not in fresh or not _finite(data.get(symbol))
               for symbol in (benchmark,) + AI_PROXIES):
            return {"regime": "INSUFFICIENT_DATA", "candidates": [], "trade_signal": False}
        if sum(symbol in fresh and _finite(data.get(symbol)) for symbol in SECTORS) < 6:
            return {"regime": "INSUFFICIENT_DATA", "candidates": [], "trade_signal": False}
    five, twenty = windows["5d"], windows["20d"]
    ai5 = sum(five[s] for s in AI_PROXIES) / len(AI_PROXIES)
    ai20 = sum(twenty[s] for s in AI_PROXIES) / len(AI_PROXIES)
    confirmed = []
    for symbol in SECTORS:
        if not all(symbol in freshness[window] and _finite(windows[window].get(symbol))
                   for window in ("5d", "20d")):
            continue
        relative5 = five[symbol] - five[benchmark]
        relative20 = twenty[symbol] - twenty[benchmark]
        if min(five[symbol], twenty[symbol], relative5, relative20) > 0:
            confirmed.append({"symbol": symbol, "relative_5d_pct": round(relative5, 3),
                              "relative_20d_pct": round(relative20, 3)})
    confirmed.sort(key=lambda row: (-row["relative_20d_pct"], -row["relative_5d_pct"], row["symbol"]))
    if ai5 >= five[benchmark] or ai20 >= twenty[benchmark]:
        regime = "AI_LEADING_OR_MIXED"
        confirmed = []
    elif confirmed:
        regime = "CONFIRMED_RELATIVE_ROTATION"
    elif five[benchmark] < 0 and twenty[benchmark] < 0:
        regime = "BROAD_RISK_OFF"
    else:
        regime = "MIXED"
    return {"regime": regime, "candidates": confirmed, "trade_signal": False,
            "note": "Confirmed relative price strength, not measured fund flows."}
