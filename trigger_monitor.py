"""
AI Market Radar V5.2 - Trigger Monitor V1

Read-only intraday quote helper for the browser-side Trigger Monitor.
No order placement. Existing decision engines remain authoritative.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

_QUOTE_CACHE = {}
_QUOTE_TTL_SECONDS = 10


def _safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _normalize_frame(frame, ticker):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        target = str(ticker).strip().upper()
        price_names = {"Open", "High", "Low", "Close", "Volume"}
        price_level = None
        for level in range(out.columns.nlevels):
            vals = list(out.columns.get_level_values(level))
            if any(v in price_names for v in vals):
                price_level = level
                break
        if price_level is not None:
            other_levels = [i for i in range(out.columns.nlevels) if i != price_level]
            for level in other_levels:
                vals = out.columns.get_level_values(level)
                mask = [str(v).strip().upper() == target for v in vals]
                if any(mask):
                    out = out.loc[:, mask].copy()
                    break
            out.columns = out.columns.get_level_values(price_level)
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()].copy()
    return out


def _timestamp_iso(index_value):
    if index_value is None:
        return None
    try:
        ts = pd.Timestamp(index_value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.isoformat()
    except Exception:
        return None


def get_intraday_quote(ticker, force=False):
    symbol = str(ticker or "").strip().upper()
    if not symbol or len(symbol) > 12:
        raise ValueError("ticker ไม่ถูกต้อง")

    now = time.time()
    cached = _QUOTE_CACHE.get(symbol)
    if cached and not force and now - cached["cached_at"] < _QUOTE_TTL_SECONDS:
        return dict(cached["data"])

    attempts = []
    frame = None

    try:
        frame = yf.Ticker(symbol).history(
            period="1d",
            interval="1m",
            prepost=True,
            auto_adjust=False,
        )
        frame = _normalize_frame(frame, symbol)
    except Exception as exc:
        attempts.append(str(exc))

    if frame is None or frame.empty or "Close" not in frame.columns:
        try:
            frame = yf.download(
                symbol,
                period="1d",
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=10,
            )
            frame = _normalize_frame(frame, symbol)
        except Exception as exc:
            attempts.append(str(exc))

    if frame is None or frame.empty or "Close" not in frame.columns:
        raise ValueError("ไม่พบราคานาทีล่าสุดจากแหล่งข้อมูลฟรี")

    closes = frame["Close"].dropna()
    if closes.empty:
        raise ValueError("ข้อมูลราคาล่าสุดว่าง")

    price = _safe_float(closes.iloc[-1])
    if price is None or price <= 0:
        raise ValueError("อ่านราคาล่าสุดไม่ได้")

    last_index = closes.index[-1]
    ts_iso = _timestamp_iso(last_index)

    age_seconds = None
    if ts_iso:
        try:
            ts = datetime.fromisoformat(ts_iso)
            age_seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
        except Exception:
            age_seconds = None

    data = {
        "ticker": symbol,
        "price": round(price, 4),
        "timestamp_utc": ts_iso,
        "age_seconds": age_seconds,
        "source": "Yahoo 1m",
        "read_only": True,
    }
    _QUOTE_CACHE[symbol] = {"cached_at": now, "data": data}
    return dict(data)


def classify_trigger(price, trigger, buy_high, consecutive_hits=0):
    p = _safe_float(price)
    t = _safe_float(trigger)
    hi = _safe_float(buy_high)
    hits = max(0, int(consecutive_hits or 0))

    if p is None or t is None or hi is None or t <= 0 or hi < t:
        return {"state": "INVALID", "hits": 0}

    if p < t:
        return {"state": "BELOW_TRIGGER", "hits": 0}

    # Small tolerance above Buy Zone is observation-only. Beyond this, do not chase.
    if p > hi * 1.005:
        return {"state": "DONT_CHASE", "hits": hits}

    hits += 1
    if hits >= 2:
        return {"state": "TRIGGER_CONFIRMED", "hits": hits}

    return {"state": "TRIGGER_TOUCHED", "hits": hits}
