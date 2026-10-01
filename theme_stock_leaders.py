import math
import time

import pandas as pd
import yfinance as yf

from multi_radar import _load_config, _series, _ret, _ema20_state, _volume_ratio

_CACHE = {}
_CACHE_TTL = 10 * 60


def _download_theme(config, theme_key):
    theme = config["themes"].get(theme_key)
    if not theme:
        raise ValueError("Unknown Multi-Radar theme")
    symbols = sorted(set([config["benchmark"], theme["proxy"], *theme["members"]]))
    data = yf.download(
        symbols,
        period="6mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
        timeout=20,
    )
    if data is None or data.empty:
        raise ValueError("Theme stock-leader market data unavailable")
    return data


def _clip(value, low, high):
    return max(low, min(high, value))


def _pct_rank(values, value):
    clean = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not clean:
        return 50.0
    less = sum(1 for x in clean if x < value)
    equal = sum(1 for x in clean if x == value)
    return (less + 0.5 * equal) / len(clean) * 100.0


def _stock_snapshot(data, ticker, benchmark, proxy, end=None):
    close = _series(data, ticker, "Close")
    bench_close = _series(data, benchmark, "Close")
    proxy_close = _series(data, proxy, "Close")
    close_at = close if end is None else close.loc[:end]
    bench_at = bench_close if end is None else bench_close.loc[:end]
    proxy_at = proxy_close if end is None else proxy_close.loc[:end]
    if min(len(close_at), len(bench_at), len(proxy_at)) < 22:
        return None

    r1 = _ret(close, 1, end)
    r5 = _ret(close, 5, end)
    r20 = _ret(close, 20, end)
    p1 = _ret(proxy_close, 1, end)
    p5 = _ret(proxy_close, 5, end)
    p20 = _ret(proxy_close, 20, end)
    b5 = _ret(bench_close, 5, end)
    if None in (r1, r5, r20, p1, p5, p20, b5):
        return None

    ema20 = _ema20_state(close, end)
    volume_ratio = _volume_ratio(data, ticker, end)
    last = float(close_at.dropna().iloc[-1])
    return {
        "ticker": ticker,
        "price": round(last, 2),
        "return_1d_pct": round(r1, 2),
        "return_5d_pct": round(r5, 2),
        "return_20d_pct": round(r20, 2),
        "relative_proxy_1d_pct": round(r1 - p1, 2),
        "relative_proxy_5d_pct": round(r5 - p5, 2),
        "relative_proxy_20d_pct": round(r20 - p20, 2),
        "relative_qqq_5d_pct": round(r5 - b5, 2),
        "above_ema20": bool(ema20) if ema20 is not None else False,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
    }


def _rank_stocks(rows):
    if not rows:
        return []
    rel1 = [x["relative_proxy_1d_pct"] for x in rows]
    rel5 = [x["relative_proxy_5d_pct"] for x in rows]
    rel20 = [x["relative_proxy_20d_pct"] for x in rows]
    volumes = [x["volume_ratio"] for x in rows if x["volume_ratio"] is not None]

    ranked = []
    for row in rows:
        p1 = _pct_rank(rel1, row["relative_proxy_1d_pct"])
        p5 = _pct_rank(rel5, row["relative_proxy_5d_pct"])
        p20 = _pct_rank(rel20, row["relative_proxy_20d_pct"])
        pv = _pct_rank(volumes, row["volume_ratio"]) if row["volume_ratio"] is not None else 50.0
        ema = 100.0 if row["above_ema20"] else 0.0

        score = (
            p5 * 0.30
            + p20 * 0.25
            + p1 * 0.20
            + pv * 0.15
            + ema * 0.10
        )
        checks = {
            "beats_proxy_1d": row["relative_proxy_1d_pct"] > 0,
            "beats_proxy_5d": row["relative_proxy_5d_pct"] > 0,
            "beats_proxy_20d": row["relative_proxy_20d_pct"] > 0,
            "above_ema20": row["above_ema20"],
            "volume_confirmed": (row["volume_ratio"] or 0) >= 1.0,
        }
        confirmations = sum(1 for ok in checks.values() if ok)
        item = dict(row)
        item.update({
            "leader_score": round(_clip(score, 0.0, 100.0), 1),
            "confirmation_count": confirmations,
            "confirmation_total": len(checks),
            "checks": checks,
        })
        ranked.append(item)

    ranked.sort(
        key=lambda x: (
            -(1 if x["confirmation_count"] >= 4 else 0),
            -x["leader_score"],
            -x["confirmation_count"],
            -x["relative_proxy_5d_pct"],
        )
    )
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
        if idx == 1 and row["confirmation_count"] >= 4:
            row["state"] = "GROUP_LEADER"
            row["state_label"] = "Group Leader"
        elif row["confirmation_count"] >= 3:
            row["state"] = "CONTENDER"
            row["state_label"] = "Contender"
        else:
            row["state"] = "WATCH"
            row["state_label"] = "Watch"
    return ranked


def build_theme_stock_leaders(theme_key, force=False):
    key = str(theme_key or "").strip().lower()
    config = _load_config()
    theme = config["themes"].get(key)
    if not theme:
        raise ValueError("Unknown Multi-Radar theme")

    now = time.time()
    cached = _CACHE.get(key)
    if not force and cached and now - cached["ts"] < _CACHE_TTL:
        payload = dict(cached["payload"])
        payload["cached"] = True
        return payload

    data = _download_theme(config, key)
    rows = []
    for ticker in theme["members"]:
        item = _stock_snapshot(data, ticker, config["benchmark"], theme["proxy"])
        if item:
            rows.append(item)

    ranked = _rank_stocks(rows)
    payload = {
        "version": "5.1-stock-bridge",
        "theme_key": key,
        "theme_label": theme["label"],
        "proxy": theme["proxy"],
        "benchmark": config["benchmark"],
        "stocks": ranked,
        "top3": ranked[:3],
        "leader": ranked[0] if ranked else None,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
        "note": (
            "Stock Leader Score ranks members inside the selected theme using relative "
            "1D/5D/20D momentum, EMA20 participation and volume. It does not replace "
            "the existing AI Top Pick / Premarket / Opening decision flow."
        ),
    }
    _CACHE[key] = {"ts": now, "payload": payload}
    return payload
