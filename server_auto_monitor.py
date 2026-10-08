"""
AI Market Radar V5.3.1 - Premarket Prep + Live Candidate Rotation

Read-only / alert-only server monitor. Existing scoring and decision engines
remain authoritative and unchanged.

Server flow:
08:30-09:20 ET  Premarket preparation + ranking refresh
09:20-09:30 ET  Premarket candidate lock
09:30-09:45 ET  Opening range collection
09:45-16:00 ET  Live monitor + periodic Top Pick re-ranking

Live Top Pick rotation uses hysteresis:
- existing active candidates are retained through small rank changes
- a challenger must beat the weakest active candidate by a score margin
- challenger must persist for multiple re-rank cycles
- a candidate with a touched/confirmed trigger is not displaced by a routine rank change
- invalid/CACHED/SKIP/high-impact-negative candidates are removed immediately

No brokerage connection. No order placement.
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
_RERANK_SECONDS = max(180, int(os.getenv("SERVER_LIVE_RERANK_SECONDS", "300") or 300))
_SWITCH_MARGIN = max(1.0, float(os.getenv("SERVER_LIVE_SWITCH_MARGIN", "4") or 4))
_SWITCH_CONFIRMATIONS = max(1, int(os.getenv("SERVER_LIVE_SWITCH_CONFIRMATIONS", "2") or 2))
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
    "candidate_mode": None,
    "active_queue": [],
    "ranking": [],
    "premarket": [],
    "candidates": [],
    "alerts": [],
    "last_rerank_at": None,
    "rotation_events": [],
}

_HITS = {}
_ALERTED = {}
_ACTIVE = {}
_CHALLENGER_STREAK = {}
_LAST_RERANK_TS = 0.0
_PREMARKET_HISTORY = {}


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


def _previous_close(frame, today):
    prev_rows = frame[frame.index.date < today]
    prev_rth = prev_rows[
        (prev_rows.index.time >= dtime(9, 30))
        & (prev_rows.index.time <= dtime(16, 0))
    ]
    if prev_rth.empty or "Close" not in prev_rth.columns:
        return None
    closes = prev_rth["Close"].dropna()
    return _safe_float(closes.iloc[-1]) if not closes.empty else None


def get_premarket_snapshot(ticker, now_et=None):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        raise ValueError("ticker missing")
    now_et = now_et or datetime.now(ET)
    frame = _intraday_frame(symbol)
    today = now_et.date()
    today_rows = frame[frame.index.date == today]
    premarket = today_rows[
        (today_rows.index.time >= dtime(4, 0))
        & (today_rows.index.time < dtime(9, 30))
    ]

    if premarket.empty or "Close" not in premarket.columns:
        return {"ok": False, "reason": "premarket_not_ready", "ticker": symbol}

    closes = premarket["Close"].dropna()
    if closes.empty:
        return {"ok": False, "reason": "premarket_close_missing", "ticker": symbol}

    latest_ts = closes.index[-1]
    last = _safe_float(closes.iloc[-1])
    prev_close = _previous_close(frame, today)
    high = _safe_float(premarket["High"].max()) if "High" in premarket.columns else None
    low = _safe_float(premarket["Low"].min()) if "Low" in premarket.columns else None
    pct = ((last / prev_close) - 1.0) * 100.0 if last and prev_close else None
    age_seconds = max(0, int((now_et - latest_ts.to_pydatetime()).total_seconds()))

    return {
        "ok": all(v is not None for v in (last, prev_close, high, low, pct)),
        "reason": None,
        "ticker": symbol,
        "price": last,
        "previous_close": prev_close,
        "premarket_pct": pct,
        "premarket_high": high,
        "premarket_low": low,
        "timestamp_et": latest_ts.isoformat(),
        "age_seconds": age_seconds,
        "source": "Yahoo 1m prepost",
    }


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
    prev_close = _previous_close(frame, today)

    premarket = today_rows[
        (today_rows.index.time >= dtime(4, 0))
        & (today_rows.index.time < dtime(9, 30))
    ]
    premarket_last = None
    if not premarket.empty and "Close" in premarket.columns and not premarket["Close"].dropna().empty:
        premarket_last = _safe_float(premarket["Close"].dropna().iloc[-1])
    premarket_pct = ((premarket_last / prev_close) - 1.0) * 100.0 if prev_close and premarket_last else None

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
    if t < dtime(8, 30):
        return "PREMARKET_COLLECT"
    if t < dtime(9, 20):
        return "PREMARKET_PREP"
    if t < dtime(9, 30):
        return "PREMARKET_LOCK"
    if t < dtime(9, 45):
        return "OPENING_RANGE"
    if t <= dtime(16, 0):
        return "RTH_MONITOR"
    return "AFTER_CLOSE"


def _eligible_ranked(force=False):
    top = base.build_top_picks(force=force)
    picks = list(top.get("top_picks") or [])
    out = []
    for x in picks:
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


def _rank_summary(rows):
    return [
        {
            "ticker": x.get("ticker"),
            "pick_rank": x.get("pick_rank"),
            "watch_score": x.get("watch_score"),
            "pick_code": x.get("pick_code"),
            "group": x.get("group"),
        }
        for x in rows[:8]
    ]


def _rotation_event(now_et, old_ticker, new_ticker, reason):
    event = {
        "time_et": now_et.isoformat(),
        "out": old_ticker,
        "in": new_ticker,
        "reason": reason,
    }
    with _LOCK:
        _STATE["rotation_events"] = (_STATE.get("rotation_events") or [])[-19:] + [event]


def _refresh_active_queue(now_et, force=False):
    global _LAST_RERANK_TS

    ranked = _eligible_ranked(force=force)
    by_ticker = {str(x.get("ticker") or "").upper(): x for x in ranked}
    eligible_order = [str(x.get("ticker") or "").upper() for x in ranked]

    # Remove candidates that became invalid or disappeared from the eligible list.
    for ticker in list(_ACTIVE):
        if ticker not in by_ticker:
            _ACTIVE.pop(ticker, None)
            _HITS.pop(ticker, None)
            _rotation_event(now_et, ticker, None, "candidate no longer eligible")

    # Refresh the payload for still-active candidates.
    for ticker in list(_ACTIVE):
        if ticker in by_ticker:
            _ACTIVE[ticker] = by_ticker[ticker]

    # Fill empty slots from current rank order.
    for ticker in eligible_order:
        if len(_ACTIVE) >= _MAX_CANDIDATES:
            break
        if ticker not in _ACTIVE:
            _ACTIVE[ticker] = by_ticker[ticker]
            _rotation_event(now_et, None, ticker, "filled open candidate slot")

    # Hysteresis replacement: challenger needs a clear margin and persistence.
    active_scores = {
        t: float((_ACTIVE[t].get("watch_score") or 0))
        for t in _ACTIVE
    }
    challengers = [t for t in eligible_order if t not in _ACTIVE]

    for challenger in challengers:
        replaceable = [
            t for t in _ACTIVE
            if int(_HITS.get(t, 0)) == 0
        ]
        if not replaceable:
            break
        weakest = min(replaceable, key=lambda t: active_scores.get(t, 0))
        challenger_score = float(by_ticker[challenger].get("watch_score") or 0)
        weakest_score = active_scores.get(weakest, 0)

        if challenger_score >= weakest_score + _SWITCH_MARGIN:
            _CHALLENGER_STREAK[challenger] = int(_CHALLENGER_STREAK.get(challenger, 0)) + 1
        else:
            _CHALLENGER_STREAK[challenger] = 0

        if _CHALLENGER_STREAK[challenger] >= _SWITCH_CONFIRMATIONS:
            _ACTIVE.pop(weakest, None)
            _HITS.pop(weakest, None)
            _ACTIVE[challenger] = by_ticker[challenger]
            _CHALLENGER_STREAK[challenger] = 0
            _rotation_event(
                now_et,
                weakest,
                challenger,
                f"challenger +{challenger_score - weakest_score:.1f} score for {_SWITCH_CONFIRMATIONS} reranks",
            )
            break

    # Clean challenger streaks no longer present.
    for ticker in list(_CHALLENGER_STREAK):
        if ticker not in by_ticker or ticker in _ACTIVE:
            _CHALLENGER_STREAK.pop(ticker, None)

    _LAST_RERANK_TS = time.time()
    with _LOCK:
        _STATE["ranking"] = _rank_summary(ranked)
        _STATE["active_queue"] = _rank_summary(list(_ACTIVE.values()))
        _STATE["last_rerank_at"] = now_et.isoformat()

    return list(_ACTIVE.values())


def _maybe_rerank(now_et, force=False):
    if force or not _ACTIVE or time.time() - _LAST_RERANK_TS >= _RERANK_SECONDS:
        return _refresh_active_queue(now_et, force=True)
    return list(_ACTIVE.values())


def _premarket_row(candidate, now_et):
    ticker = str(candidate.get("ticker") or "").upper()
    snap = get_premarket_snapshot(ticker, now_et=now_et)
    lo = _safe_float(candidate.get("buy_low"))
    hi = _safe_float(candidate.get("buy_high"))
    price = _safe_float(snap.get("price"))
    distance = None
    if price is not None and lo:
        distance = (price / lo - 1.0) * 100.0

    if not snap.get("ok"):
        state = "DATA_NOT_READY"
    elif snap.get("age_seconds") is None or int(snap.get("age_seconds")) > 180:
        state = "STALE_DATA"
    elif snap.get("premarket_pct") is not None and float(snap["premarket_pct"]) < -5:
        state = "PM_BLOCK"
    elif snap.get("premarket_pct") is not None and float(snap["premarket_pct"]) >= 5:
        state = "PM_HOT"
    elif price is not None and lo is not None and hi is not None and lo <= price <= hi:
        state = "PM_IN_BUY_ZONE"
    elif price is not None and lo is not None and price < lo:
        state = "PM_BELOW_TRIGGER"
    else:
        state = "PM_ABOVE_ZONE"

    row = {
        "ticker": ticker,
        "pick_rank": candidate.get("pick_rank"),
        "watch_score": candidate.get("watch_score"),
        "buy_low": lo,
        "buy_high": hi,
        "distance_to_trigger_pct": distance,
        "snapshot": snap,
        "state": state,
    }

    key = str(now_et.date()) + ":" + ticker
    hist = _PREMARKET_HISTORY.setdefault(key, [])
    hist.append({
        "time_et": now_et.isoformat(),
        "price": price,
        "premarket_pct": snap.get("premarket_pct"),
        "state": state,
    })
    if len(hist) > 60:
        del hist[:-60]
    return row


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
        "premarket": [],
        "alerts": [],
    }

    # Reset per-session trigger/ranking state before the useful premarket window.
    if window in {"CLOSED_WEEKEND", "AFTER_CLOSE"}:
        with _LOCK:
            _STATE["session"] = window
            _STATE["candidate_mode"] = "IDLE"
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["candidates"] = []
            _STATE["premarket"] = []
        return summary

    if window == "PREMARKET_COLLECT":
        with _LOCK:
            _STATE["session"] = window
            _STATE["candidate_mode"] = "COLLECT_ONLY"
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["candidates"] = []
        return summary

    if window == "PREMARKET_PREP":
        candidates = _maybe_rerank(now_et)
        for candidate in candidates:
            try:
                summary["premarket"].append(_premarket_row(candidate, now_et))
            except Exception as exc:
                summary["premarket"].append({
                    "ticker": str(candidate.get("ticker") or "").upper(),
                    "state": "ERROR",
                    "error": str(exc),
                })
        with _LOCK:
            _STATE["session"] = window
            _STATE["candidate_mode"] = "DYNAMIC_PREMARKET"
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["premarket"] = summary["premarket"]
            _STATE["candidates"] = []
        return summary

    if window == "PREMARKET_LOCK":
        if not _ACTIVE:
            _maybe_rerank(now_et, force=True)
        for candidate in list(_ACTIVE.values()):
            try:
                summary["premarket"].append(_premarket_row(candidate, now_et))
            except Exception as exc:
                summary["premarket"].append({
                    "ticker": str(candidate.get("ticker") or "").upper(),
                    "state": "ERROR",
                    "error": str(exc),
                })
        with _LOCK:
            _STATE["session"] = window
            _STATE["candidate_mode"] = "PREMARKET_LOCKED"
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["premarket"] = summary["premarket"]
        return summary

    if window == "OPENING_RANGE":
        if not _ACTIVE:
            _maybe_rerank(now_et, force=True)
        with _LOCK:
            _STATE["session"] = window
            _STATE["candidate_mode"] = "OPENING_RANGE_LOCK"
            _STATE["last_cycle_at"] = now_et.isoformat()
            _STATE["candidates"] = []
        return summary

    # RTH: periodically re-rank and rotate the live candidate queue.
    candidates = _maybe_rerank(now_et)
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
        _STATE["candidate_mode"] = "LIVE_ROTATION"
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
    out["rerank_seconds"] = _RERANK_SECONDS
    out["switch_margin"] = _SWITCH_MARGIN
    out["switch_confirmations"] = _SWITCH_CONFIRMATIONS
    out["enabled"] = _ENABLED
    return out
