import json
import math
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = BASE_DIR / "multi_radar_universe.json"
_CACHE = {"ts": 0.0, "payload": None}
_CACHE_TTL = 10 * 60


def _load_config():
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _flatten(data):
    if isinstance(data.columns, pd.MultiIndex):
        return data
    return data


def _series(data, ticker, field):
    if not isinstance(data.columns, pd.MultiIndex):
        if field in data.columns:
            return data[field].dropna()
        return pd.Series(dtype=float)
    for key in ((field, ticker), (ticker, field)):
        if key in data.columns:
            return data[key].dropna()
    return pd.Series(dtype=float)


def _ret(series, lookback, end=None):
    s = series if end is None else series.loc[:end]
    s = s.dropna()
    if len(s) <= lookback:
        return None
    a = float(s.iloc[-lookback - 1])
    b = float(s.iloc[-1])
    if not a or not math.isfinite(a) or not math.isfinite(b):
        return None
    return (b / a - 1.0) * 100.0


def _ema20_state(series, end=None):
    s = series if end is None else series.loc[:end]
    s = s.dropna()
    if len(s) < 20:
        return None
    ema = s.ewm(span=20, adjust=False).mean().iloc[-1]
    return bool(float(s.iloc[-1]) > float(ema))


def _volume_ratio(data, ticker, end=None):
    v = _series(data, ticker, "Volume")
    if end is not None:
        v = v.loc[:end]
    v = v.dropna()
    if len(v) < 21:
        return None
    avg = float(v.iloc[-21:-1].mean())
    cur = float(v.iloc[-1])
    if avg <= 0:
        return None
    return cur / avg


def _download(config):
    symbols = {config["benchmark"]}
    for theme in config["themes"].values():
        symbols.add(theme["proxy"])
        symbols.update(theme["members"])
    data = yf.download(
        sorted(symbols),
        period="6mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
        timeout=20,
    )
    if data is None or data.empty:
        raise ValueError("Multi-Radar market data unavailable")
    return _flatten(data)


def _safe_mean(values):
    values = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return sum(values) / len(values) if values else None


def _safe_median(values):
    values = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if not values:
        return None
    n = len(values)
    m = n // 2
    return values[m] if n % 2 else (values[m - 1] + values[m]) / 2.0


def _score_theme(data, benchmark, theme, end=None):
    bench_close = _series(data, benchmark, "Close")
    proxy_close = _series(data, theme["proxy"], "Close")
    bench5, bench20 = _ret(bench_close, 5, end), _ret(bench_close, 20, end)
    proxy5, proxy20 = _ret(proxy_close, 5, end), _ret(proxy_close, 20, end)
    if None in (bench5, bench20, proxy5, proxy20):
        return None

    rel5 = proxy5 - bench5
    rel20 = proxy20 - bench20
    member_rel20, breadth5, above20, vr = [], [], [], []
    valid = 0
    for ticker in theme["members"]:
        close = _series(data, ticker, "Close")
        r5, r20 = _ret(close, 5, end), _ret(close, 20, end)
        if r5 is None or r20 is None:
            continue
        valid += 1
        member_rel20.append(r20 - bench20)
        breadth5.append(1 if r5 > bench5 else 0)
        state = _ema20_state(close, end)
        if state is not None:
            above20.append(1 if state else 0)
        ratio = _volume_ratio(data, ticker, end)
        if ratio is not None:
            vr.append(max(0.0, min(3.0, ratio)))
    if valid < 3:
        return None
    breadth_pct = 100.0 * _safe_mean(breadth5)
    above_pct = 100.0 * _safe_mean(above20) if above20 else 50.0
    med_rel20 = _safe_median(member_rel20) or 0.0
    volume_ratio = _safe_median(vr) or 1.0
    volume_component = max(-1.0, min(1.0, volume_ratio - 1.0))

    raw = (
        rel5 * 4.0
        + rel20 * 1.8
        + med_rel20 * 1.2
        + (breadth_pct - 50.0) * 0.22
        + (above_pct - 50.0) * 0.12
        + volume_component * 8.0
    )
    score = round(max(-100.0, min(100.0, raw)), 1)
    return {
        "proxy": theme["proxy"],
        "member_count": valid,
        "score": score,
        "proxy_rel_5d_pct": round(rel5, 2),
        "proxy_rel_20d_pct": round(rel20, 2),
        "member_median_rel_20d_pct": round(med_rel20, 2),
        "breadth_5d_pct": round(breadth_pct, 1),
        "above_ema20_pct": round(above_pct, 1),
        "volume_ratio_median": round(volume_ratio, 2),
    }


def _transition_metrics(key, history):
    points = []
    for day in history:
        row = next((x for x in day.get("ranking", []) if x.get("key") == key), None)
        if row:
            points.append({"score": float(row["score"]), "rank": int(row["rank"])})
    if not points:
        return {"score_change_1d": 0.0, "score_change_5d": 0.0, "rank_change_5d": 0}

    latest = points[-1]
    prev = points[-2] if len(points) >= 2 else latest
    base5 = points[-6] if len(points) >= 6 else points[0]
    return {
        "score_change_1d": round(latest["score"] - prev["score"], 1),
        "score_change_5d": round(latest["score"] - base5["score"], 1),
        "rank_change_5d": int(base5["rank"] - latest["rank"]),
    }


def _state(score, rank, metrics):
    d1 = float(metrics.get("score_change_1d") or 0)
    d5 = float(metrics.get("score_change_5d") or 0)
    rank5 = int(metrics.get("rank_change_5d") or 0)

    if rank == 1 and score >= 12 and d5 >= -4:
        return "LEADING", "Leading"
    if score >= 8 and d5 <= -6:
        return "COOLING", "Cooling"
    if score >= 8 and (d1 >= 2 or d5 >= 6) and d5 > -6 and rank <= 4:
        return "ACCELERATING", "Accelerating"
    if score < 12 and d5 >= 8 and rank5 >= 1 and rank <= 4:
        return "EARLY_ROTATION", "Early Rotation"
    if score <= -12 and d5 > 8 and rank5 >= 1:
        return "EARLY_ROTATION", "Early Rotation"
    if score <= -12:
        return "LAGGING", "Lagging"
    if d5 <= -8 and rank5 <= -1:
        return "COOLING", "Cooling"
    return "NEUTRAL", "Neutral"


def _history(data, config, sessions=15):
    benchmark = config["benchmark"]
    bench = _series(data, benchmark, "Close")
    dates = list(bench.dropna().index[-sessions:])
    trail = []
    for end in dates:
        rows = []
        for key, theme in config["themes"].items():
            scored = _score_theme(data, benchmark, theme, end=end)
            if scored:
                rows.append({"key": key, "label": theme["label"], "score": scored["score"]})
        rows.sort(key=lambda x: x["score"], reverse=True)
        for idx, row in enumerate(rows, start=1):
            row["rank"] = idx
        if rows:
            trail.append({
                "date": pd.Timestamp(end).strftime("%Y-%m-%d"),
                "leader": rows[0]["key"],
                "leader_label": rows[0]["label"],
                "leader_score": rows[0]["score"],
                "ranking": rows,
            })
    return trail


def build_multi_radar(force=False):
    now = time.time()
    if not force and _CACHE["payload"] and now - _CACHE["ts"] < _CACHE_TTL:
        payload = dict(_CACHE["payload"])
        payload["cached"] = True
        return payload

    config = _load_config()
    data = _download(config)
    benchmark = config["benchmark"]
    hist = _history(data, config, sessions=15)

    themes = []
    for key, theme in config["themes"].items():
        scored = _score_theme(data, benchmark, theme)
        if not scored:
            continue
        scored.update({"key": key, "label": theme["label"]})
        themes.append(scored)

    themes.sort(key=lambda x: x["score"], reverse=True)
    for idx, row in enumerate(themes, start=1):
        row["rank"] = idx
        metrics = _transition_metrics(row["key"], hist)
        row.update(metrics)
        row["acceleration"] = metrics["score_change_1d"]
        row["state"], row["state_label"] = _state(row["score"], idx, metrics)

    leader = themes[0] if themes else None
    early_rotation = [x for x in themes if x["state"] == "EARLY_ROTATION"]
    accelerating = [x for x in themes if x["state"] == "ACCELERATING"]
    cooling = [x for x in themes if x["state"] == "COOLING"]
    transition = {
        "early_rotation": early_rotation,
        "accelerating": accelerating,
        "cooling": cooling,
        "watch_first": (early_rotation + accelerating)[:3],
    }
    payload = {
        "version": "5.1",
        "benchmark": benchmark,
        "themes": themes,
        "leader": leader,
        "history": hist,
        "transition": transition,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cached": False,
        "note": (
            "Rotation Score combines theme-proxy relative momentum, member breadth, "
            "EMA20 participation and volume confirmation. It is a ranking signal, not a buy signal."
        ),
    }
    _CACHE["ts"], _CACHE["payload"] = now, payload
    return payload
