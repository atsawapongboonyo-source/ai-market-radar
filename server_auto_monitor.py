"""
AI Market Radar V5.3 - Server Auto Monitor

Read-only, alert-only background monitor for the existing Top Pick pipeline.
It does not place orders and it does not change any scoring/decision formula.

Flow:
Top Picks -> Yahoo 1m auto data -> Trigger confirmation -> existing Opening
Confirmation -> existing Final Decision -> Telegram ENTRY SIGNAL.

Fail closed:
- weekdays only
- RTH monitoring starts after the first 15 minutes (09:45 ET)
- stale/missing/wrong-date intraday data never confirms an entry
- negative high-impact catalyst never confirms an entry
"""

from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

import legacy_scanner as base
from telegram_alerts import send_entry_alert

ET = ZoneInfo("America/New_York")

_POLL_SECONDS = max(20, int(os.getenv("SERVER_AUTO_MONITOR_POLL_SECONDS", "30") or 30))
_MAX_CANDIDATES = max(1, min(5, int(os.getenv("SERVER_AUTO_MONITOR_MAX_CANDIDATES", "3") or 3)))
_ENABLED = str(os.getenv("SERVER_AUTO_MONITOR_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}

_LOCK = threading.Lock()
_THREAD = None
_STOP = threading.Event()
_STATE = {
    "enabled": _ENABLED,
    "running": False,
    "started_at": None,
    "last_cycle_at": None,
    "last_error": None,
    "session": None,
    "candidates": [],
    "alerts": [],
}
_HITS = {}
_ALERTED = {}


def _safe_float(v):
    try:
        if v is None or pd.isna(v):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
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
            for level in range(out.columns.nlevels):
                if level == price_level:
                    continue
                vals = out.columns.get_level_values(level)
                mask = [str(v).strip().upper() == target for v in vals]
                if any(mask):
                    out = out.loc[:, mask].copy()
                    break
            out.columns = out.columns.get_level_values(price_level)
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()].copy()
    return out


def _intraday_frame(symbol):
    errors = []
    frame = None
    try:
        frame = yf.Ticker(symbol).history(
            period="2d",
            interval="1m",
            prepost=True,
            auto_adjust=False,
        )
        frame = _normalize_frame(frame, symbol)
    except Exception as exc:
        errors.append(str(exc))

    if frame is None or frame.empty:
        try:
            frame = yf.download(
                symbol,
                period="2d",
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=10,
            )
            frame = _normalize_frame(frame, symbol)
        except Exception as exc:
            errors.append(str(exc))

    if frame is None or frame.empty:
        raise ValueError("intraday data unavailable: " + " | ".join(errors[-2:]))

    idx = pd.DatetimeIndex(frame.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(ET)
    frame = frame.copy()
    frame.index = idx
    return frame


def get_session_snapshot(ticker, now_et=None):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        raise ValueError("ticker missing")

    now_et = now_et or datetime.now(ET)
    frame = _intraday_frame(symbol)
    today = now_et.date()

    today_rows = frame[frame.index.date == today]
    if today_rows.empty:
        return {"ok": False, "reason": "no_today_data", "ticker": symbol}

    closes = today_rows["Close"].dropna() if "Close" in today_rows.columns else pd.Series(dtype=float)
    if closes.empty:
        return {"ok": False, "reason": "no_close_data", "ticker": symbol}

    latest_ts = closes.index[-1]
    price = _safe_float(closes.iloc[-1])
    age_seconds = max(0, int((now_et - latest_ts.to_pydatetime()).total_seconds()))

    # Previous regular-session close from the previous available trading date.
    prev_rows = frame[frame.index.date < today]
    prev_rth = prev_rows[
        (prev_rows.index.time >= dtime(9, 30))
        & (prev_rows.index.time <= dtime(16, 0))
    ]
    prev_close = None
    if not prev_rth.empty and "Close" in prev_rth.columns:
        prev_close = _safe_float(prev_rth["Close"].dropna().iloc[-1])

    premarket = today_rows[
        (today_rows.index.time >= dtime(4, 0))
        & (today_rows.index.time < dtime(9, 30))
    ]
    premarket_last = None
    if not premarket.empty and "Close" in premarket.columns and not premarket["Close"].dropna().empty:
        premarket_last = _safe_float(premarket["Close"].dropna().iloc[-1])

    premarket_pct = None
    if prev_close and premarket_last:
        premarket_pct = (premarket_last / prev_close - 1.0) * 100.0

    rth = today_rows[
        (today_rows.index.time >= dtime(9, 30))
        & (today_rows.index.time <= dtime(16, 0))
    ]
    if rth.empty:
        return {
            "ok": False,
            "reason": "rth_not_started",
            "ticker": symbol,
            "price": price,
            "premarket_pct": premarket_pct,
            "age_seconds": age_seconds,
        }

    # Stable 15-minute opening range. The server does not act before 09:45 ET.
    opening = rth[rth.index.time < dtime(9, 45)]
    if opening.empty:
        return {"ok": False, "reason": "opening_range_not_ready", "ticker": symbol}

    open_price = _safe_float(rth["Open"].dropna().iloc[0]) if "Open" in rth.columns else None
    opening_high = _safe_float(opening["High"].max()) if "High" in opening.columns else None
    opening_low = _safe_float(opening["Low"].min()) if "Low" in opening.columns else None

    return {
        "ok": all(v is not None for v in (price, open_price, opening_high, opening_low, premarket_pct)),
        "reason": None,
        "ticker": symbol,
        "price": price,
        "timestamp_et": latest_ts.isoformat(),
        "age_seconds": age_seconds,
        "previous_close": prev_close,
        "premarket_last": premarket_last,
        "premarket_pct": premarket_pct,
        "open_price": open_price,
        "opening_high": opening_high,
        "opening_low": opening_low,
        "source": "Yahoo 1m prepost",
    }


def _market_window(now_et):
    if now_et.weekday() >= 5:
        return "CLOSED_WEEKEND"
    t = now_et.time()
    if t < dtime(9, 30):
        return "PREMARKET"
    if t < dtime(9, 45):
        return "OPENING_RANGE"
    if t <= dtime(16, 0):
        return "RTH_MONITOR"
    return "AFTER_CLOSE"


def _candidate_payloads():
    top = base.build_top_picks(force=False)
    picks = list(top.get("top_picks") or [])
    out = []
    for x in picks:
        if len(out) >= _MAX_CANDIDATES:
            break
        if str(x.get("confidence_code") or "").upper() == "CACHED":
            continue
        if bool((x.get("catalyst") or {}).get("negative_high_impact")):
            continue
        if str(x.get("pick_code") or "").upper() == "SKIP":
            continue
        required = ("ticker", "buy_low", "buy_high", "stop", "tp1")
        if any(x.get(k) in (None, "") for k in required):
            continue
        out.append(x)
    return out


def _signal_key(ticker, session_date):
    return str(session_date) + ":" + str(ticker).upper()


def _evaluate_candidate(candidate, now_et):
    ticker = str(candidate.get("ticker") or "").upper()
    snap = get_session_snapshot(ticker, now_et=now_et)
    row = {
        "ticker": ticker,
        "pick_rank": candidate.get("pick_rank"),
        "watch_score": candidate.get("watch_score"),
        "buy_low": candidate.get("buy_low"),
        "buy_high": candidate.get("buy_high"),
        "snapshot": snap,
        "state": "DATA_NOT_READY",
        "opening": None,
        "final": None,
        "telegram": None,
    }

    if not snap.get("ok"):
        row["state"] = "DATA_NOT_READY"
        return row

    if snap.get("age_seconds") is None or int(snap.get("age_seconds")) > 180:
        row["state"] = "STALE_DATA"
        return row

    price = float(snap["price"])
    lo = float(candidate["buy_low"])
    hi = float(candidate["buy_high"])
    stop = float(candidate["stop"])
    tp1 = float(candidate["tp1"])

    if price < lo:
        _HITS[ticker] = 0
        row["state"] = "WATCH_BELOW_TRIGGER"
        return row

    if price > hi * 1.005:
        _HITS[ticker] = 0
        row["state"] = "DONT_CHASE"
        return row

    _HITS[ticker] = int(_HITS.get(ticker, 0)) + 1
    if _HITS[ticker] < 2:
        row["state"] = "TRIGGER_TOUCHED"
        return row

    cat = candidate.get("catalyst") or {}
    common = {
        "price": price,
        "buy_low": lo,
        "buy_high": hi,
        "stop": stop,
        "tp1": tp1,
        "premarket_pct": snap.get("premarket_pct"),
        "rel_volume": None,
        "market": candidate.get("market_state") or "unknown",
        "sector": candidate.get("group_state") or "unknown",
        "catalyst": cat.get("sentiment") or "unknown",
        "catalyst_score": cat.get("score") if cat.get("score") is not None else 50,
        "negative_high_impact": bool(cat.get("negative_high_impact")),
        "data_confidence": candidate.get("confidence_code") or "FRESH",
    }

    opening_payload = dict(common)
    opening_payload.update({
        "open_price": snap.get("open_price"),
        "opening_high": snap.get("opening_high"),
        "opening_low": snap.get("opening_low"),
    })
    opening = base._opening_confirmation(opening_payload)
    row["opening"] = opening

    if str(opening.get("state") or "").upper() != "ENTRY1":
        row["state"] = "OPENING_" + str(opening.get("state") or opening.get("status") or "WAIT").upper()
        return row

    final = base._auto_confirm(common)
    row["final"] = final
    if str(final.get("status") or "").upper() != "CONFIRMED":
        row["state"] = "FINAL_" + str(final.get("status") or "WAIT").upper()
        return row

    row["state"] = "ENTRY1_CONFIRMED"
    session_key = _signal_key(ticker, now_et.date())
    if _ALERTED.get(session_key):
        row["telegram"] = {"ok": True, "sent": False, "deduped_session": True}
        return row

    payload = {
        "ticker": ticker,
        "entry": price,
        "buy_low": lo,
        "buy_high": hi,
        "score": final.get("score"),
        "opening": "ENTRY1",
        "final_status": "CONFIRMED",
        "market": candidate.get("market_state") or "unknown",
        "group": candidate.get("group_state") or "unknown",
        "time_label": now_et.strftime("%H:%M ET"),
    }
    tg = send_entry_alert(payload)
    row["telegram"] = tg
    if tg.get("ok") and (tg.get("sent") or tg.get("deduped")):
        _ALERTED[session_key] = True
    return row


def run_cycle(now_et=None):
    now_et = now_et or datetime.now(ET)
    window = _market_window(now_et)
    summary = {
        "time_et": now_et.isoformat(),
        "window": window,
        "candidates": [],
        "alerts": [],
    }

    if window != "RTH_MONITOR":
        with _LOCK:
            _STATE["session"] = window
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["candidates"] = []
        return summary

    candidates = _candidate_payloads()
    for candidate in candidates:
        try:
            row = _evaluate_candidate(candidate, now_et)
        except Exception as exc:
            row = {
                "ticker": str(candidate.get("ticker") or "").upper(),
                "state": "ERROR",
                "error": str(exc),
            }
        summary["candidates"].append(row)
        if row.get("state") == "ENTRY1_CONFIRMED":
            summary["alerts"].append({
                "ticker": row.get("ticker"),
                "telegram": row.get("telegram"),
            })

    with _LOCK:
        _STATE["session"] = window
        _STATE["last_cycle_at"] = now_et.isoformat()
        _STATE["last_error"] = None
        _STATE["candidates"] = summary["candidates"]
        if summary["alerts"]:
            _STATE["alerts"] = (_STATE.get("alerts") or [])[-19:] + summary["alerts"]
    return summary


def _loop():
    with _LOCK:
        _STATE["running"] = True
        _STATE["started_at"] = datetime.now(ET).isoformat()
    while not _STOP.is_set():
        try:
            run_cycle()
        except Exception as exc:
            with _LOCK:
                _STATE["last_error"] = str(exc)
                _STATE["last_cycle_at"] = datetime.now(ET).isoformat()
        _STOP.wait(_POLL_SECONDS)
    with _LOCK:
        _STATE["running"] = False


def start_server_monitor():
    global _THREAD
    if not _ENABLED:
        return False
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="ai-radar-server-monitor", daemon=True)
        _THREAD.start()
    return True


def status():
    with _LOCK:
        out = dict(_STATE)
    out["poll_seconds"] = _POLL_SECONDS
    out["max_candidates"] = _MAX_CANDIDATES
    out["enabled"] = _ENABLED
    return out
