from flask import Flask, render_template, jsonify
import json
from pathlib import Path
import traceback
import math
import time

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR))

# Simple in-memory cache to reduce repeated calls to the free data source on Render.
_HISTORY_CACHE = {}
_CACHE_TTL_SECONDS = 15 * 60


def load_json(name):
    with (BASE_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_float(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        level0 = list(df.columns.get_level_values(0))
        level1 = list(df.columns.get_level_values(1))
        price_names = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
        if any(x in price_names for x in level0):
            df = df.copy()
            df.columns = df.columns.get_level_values(0)
        elif any(x in price_names for x in level1):
            df = df.copy()
            df.columns = df.columns.get_level_values(1)
    return df


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def calc_atr(df, period=14):
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        (df["High"] - df["Low"]).abs(),
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def download_history(ticker, period="1y"):
    ticker = ticker.strip().upper()
    cache_key = (ticker, period)
    now = time.time()
    cached = _HISTORY_CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1].copy()

    attempts = []
    try:
        data = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=15,
        )
        data = flatten_columns(data)
        if data is not None and not data.empty:
            _HISTORY_CACHE[cache_key] = (now, data.copy())
            return data
    except Exception as e:
        attempts.append(str(e))

    try:
        data = yf.Ticker(ticker).history(
            period=period,
            interval="1d",
            auto_adjust=False,
            timeout=15,
        )
        data = flatten_columns(data)
        if data is not None and not data.empty:
            _HISTORY_CACHE[cache_key] = (now, data.copy())
            return data
    except TypeError:
        try:
            data = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
            data = flatten_columns(data)
            if data is not None and not data.empty:
                _HISTORY_CACHE[cache_key] = (now, data.copy())
                return data
        except Exception as e:
            attempts.append(str(e))
    except Exception as e:
        attempts.append(str(e))

    raise ValueError("แหล่งข้อมูลฟรีไม่ตอบกลับหรือไม่พบข้อมูลหุ้นนี้ กรุณาลองอีกครั้งในอีกสักครู่")


def prepare_indicators(data):
    needed = ["High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in data.columns]
    if missing:
        raise ValueError("ข้อมูลย้อนหลังไม่ครบ: " + ", ".join(missing))

    data = data.dropna(subset=["High", "Low", "Close"]).copy()
    if len(data) < 60:
        raise ValueError("ข้อมูลย้อนหลังไม่เพียงพอสำหรับการคำนวณ")

    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
    data["EMA50"] = data["Close"].ewm(span=50, adjust=False).mean()
    data["RSI14"] = calc_rsi(data["Close"], 14)
    data["ATR14"] = calc_atr(data, 14)
    data["VOL20"] = data["Volume"].rolling(20).mean()
    return data


def _round(v, digits=2):
    return round(v, digits) if v is not None and math.isfinite(v) else None


def build_snapshot(data):
    """Build one decision snapshot using only rows available up to the final row."""
    last = data.iloc[-1]
    last_close = safe_float(last["Close"])
    if not last_close or last_close <= 0:
        raise ValueError("ไม่สามารถอ่านราคาปิดล่าสุดได้")

    ema20 = safe_float(last["EMA20"])
    ema50 = safe_float(last["EMA50"])
    rsi = safe_float(last["RSI14"])
    atr = safe_float(last["ATR14"]) or (last_close * 0.025)
    vol = safe_float(last["Volume"])
    vol20 = safe_float(last["VOL20"])
    vol_ratio = vol / vol20 if vol and vol20 and vol20 > 0 else None

    recent20 = data.tail(20)
    recent50 = data.tail(50)
    low20 = safe_float(recent20["Low"].min())
    high20 = safe_float(recent20["High"].max())
    high50 = safe_float(recent50["High"].max())

    support_candidates = [x for x in [low20, ema20, ema50] if x is not None and x <= last_close * 1.02]
    support = max(support_candidates) if support_candidates else low20
    if support is None:
        support = last_close - atr

    resistance_candidates = [x for x in [high20, high50] if x is not None and x >= last_close * 0.98]
    resistance = min(resistance_candidates) if resistance_candidates else None
    if resistance is None or resistance <= support:
        resistance = last_close + max(atr, last_close * 0.03)

    buy_low = support
    buy_high = min(
        support + max(atr * 0.35, last_close * 0.004),
        resistance * 0.985,
    )
    if buy_high < buy_low:
        buy_high = buy_low + max(atr * 0.2, last_close * 0.003)

    stop = max(0.01, support - max(atr * 0.55, last_close * 0.006))
    tp1 = resistance
    tp2 = resistance + max(atr * 0.65, last_close * 0.01)

    trend = "กลาง"
    if ema20 and ema50:
        if last_close > ema20 > ema50:
            trend = "ขาขึ้น"
        elif last_close < ema20 < ema50:
            trend = "ขาลง"

    # Radar Score = quality/strength of the setup, not probability of success.
    radar_score = 50
    reasons = []
    if trend == "ขาขึ้น":
        radar_score += 15
        reasons.append("ราคาอยู่เหนือ EMA20 และ EMA50")
    elif trend == "ขาลง":
        radar_score -= 15
        reasons.append("ราคาอยู่ต่ำกว่า EMA20 และ EMA50")
    else:
        reasons.append("แนวโน้ม EMA ยังไม่ชัด")

    if rsi is not None:
        if 45 <= rsi <= 65:
            radar_score += 8
            reasons.append("RSI อยู่ในโซนสมดุล")
        elif 65 < rsi <= 72:
            radar_score += 2
            reasons.append("RSI แข็งแรง แต่เริ่มเข้าโซนร้อน")
        elif rsi > 72:
            radar_score -= 8
            reasons.append("RSI ค่อนข้างร้อน")
        elif rsi < 35:
            radar_score -= 4
            reasons.append("RSI อ่อน ควรรอการยืนยัน")

    if vol_ratio is not None:
        if vol_ratio >= 1.2:
            radar_score += 7
            reasons.append("Volume สูงกว่าค่าเฉลี่ย 20 วัน")
        elif vol_ratio < 0.7:
            radar_score -= 3
            reasons.append("Volume เบากว่าปกติ")

    distance_to_support_pct = (last_close - support) / last_close * 100
    if 0 <= distance_to_support_pct <= 3:
        radar_score += 10
        reasons.append("ราคาอยู่ไม่ไกลจากแนวรับ")
    elif distance_to_support_pct > 8:
        radar_score -= 6
        reasons.append("ราคาห่างแนวรับมาก ระวังการไล่ราคา")

    radar_score = max(0, min(100, round(radar_score)))

    # Entry Score = how attractive the current entry timing is.
    entry_score = 50
    entry_reasons = []

    if trend == "ขาขึ้น":
        entry_score += 14
    elif trend == "ขาลง":
        entry_score -= 25
    else:
        entry_score -= 5

    # Price location relative to buy zone/support is the biggest component.
    if buy_low <= last_close <= buy_high:
        entry_score += 24
        entry_reasons.append("ราคาปัจจุบันอยู่ใน Buy Zone")
    elif last_close < buy_low:
        if last_close >= stop:
            entry_score += 6
            entry_reasons.append("ราคาต่ำกว่า Buy Zone แต่ยังไม่หลุดจุดที่แผนผิด")
        else:
            entry_score -= 30
            entry_reasons.append("ราคาหลุดจุดที่แผนผิด")
    else:
        gap_buy_pct = (last_close - buy_high) / last_close * 100
        gap_atr = (last_close - buy_high) / atr if atr > 0 else 0
        if gap_buy_pct <= 2.5 or gap_atr <= 0.6:
            entry_score += 5
            entry_reasons.append("ราคาเหนือ Buy Zone เล็กน้อย")
        elif gap_buy_pct <= 6 or gap_atr <= 1.25:
            entry_score -= 8
            entry_reasons.append("ราคาเริ่มห่าง Buy Zone")
        else:
            entry_score -= 22
            entry_reasons.append("ราคาห่าง Buy Zone มาก ไม่เหมาะกับการไล่ราคา")

    if rsi is not None:
        if 42 <= rsi <= 62:
            entry_score += 8
        elif rsi > 72:
            entry_score -= 12
        elif rsi < 35:
            entry_score -= 8

    if vol_ratio is not None:
        if 0.85 <= vol_ratio <= 1.8:
            entry_score += 4
        elif vol_ratio > 2.5:
            entry_score -= 4
        elif vol_ratio < 0.6:
            entry_score -= 4

    risk = max(last_close - stop, 0.01)
    reward = max(tp1 - last_close, 0)
    rr = reward / risk if risk > 0 else 0
    if rr >= 2:
        entry_score += 10
        entry_reasons.append("Risk/Reward ถึงเป้า 1 อยู่ในระดับดี")
    elif rr >= 1.2:
        entry_score += 4
    elif rr < 0.8:
        entry_score -= 12
        entry_reasons.append("Risk/Reward สำหรับการเข้าใหม่ค่อนข้างต่ำ")

    entry_score = max(0, min(100, round(entry_score)))

    # Three-step entry plan. Entry 1 is nearest/least aggressive, then deeper levels.
    entry1 = buy_high
    entry2 = support
    entry3 = max(stop + atr * 0.15, support - atr * 0.45)
    entry_levels = sorted([entry1, entry2, entry3], reverse=True)
    entry1, entry2, entry3 = entry_levels

    # Action/notice based on timing rather than Radar Score alone.
    if trend == "ขาลง" or last_close < stop or entry_score < 35:
        action_code = "AVOID"
        action_label = "🔴 ยังไม่แนะนำให้เข้า"
        action_class = "bad"
        action_note = "แนวโน้มหรือจังหวะเข้าไม่ผ่านเกณฑ์ รอสัญญาณใหม่ก่อน"
        show_entries = False
    elif buy_low <= last_close <= buy_high and entry_score >= 70:
        action_code = "ENTER"
        action_label = "🟢 เข้าไม้ 1 ได้"
        action_class = "good"
        action_note = "ราคาอยู่ในโซนเข้าและคุณภาพจังหวะผ่านเกณฑ์ แต่ยังควรเช็กข่าวและ Volume ก่อนส่งคำสั่งจริง"
        show_entries = True
    elif buy_low <= last_close <= buy_high:
        action_code = "SCALE"
        action_label = "🟢 ทยอยเข้าได้"
        action_class = "good"
        action_note = "ราคาอยู่ใน Buy Zone แต่คะแนนจังหวะยังไม่สูงพอสำหรับการเข้าเต็มแผน"
        show_entries = True
    elif last_close > buy_high:
        gap_buy_pct = (last_close - buy_high) / last_close * 100
        if gap_buy_pct > 6 or entry_score < 50:
            action_code = "DONT_CHASE"
            action_label = "🟠 ไม่แนะนำให้ไล่ราคา"
            action_class = "warn"
            action_note = "หุ้นอาจยังแข็งแรง แต่ราคาปัจจุบันห่างโซนเข้า รอ Pullback หรือฐานราคาใหม่"
        else:
            action_code = "WAIT"
            action_label = "🟡 รอจังหวะ"
            action_class = "warn"
            action_note = "ราคายังไม่เหมาะกับไม้แรก รอให้กลับเข้า Buy Zone"
        show_entries = True
    else:
        action_code = "WAIT"
        action_label = "🟡 รอการยืนยัน"
        action_class = "warn"
        action_note = "ราคาอยู่ต่ำกว่า Buy Zone ให้รอการกลับมายืนเหนือแนวรับก่อน"
        show_entries = False

    idx = data.index[-1]
    try:
        data_date = idx.strftime("%Y-%m-%d")
    except Exception:
        data_date = str(idx)[:10]

    return {
        "ticker": str(getattr(data, "name", "") or ""),
        "data_date": data_date,
        "last_close": _round(last_close),
        "ema20": _round(ema20),
        "ema50": _round(ema50),
        "rsi14": _round(rsi, 1),
        "atr14": _round(atr),
        "volume_ratio": _round(vol_ratio, 2),
        "support": _round(support),
        "resistance": _round(resistance),
        "buy_low": _round(buy_low),
        "buy_high": _round(buy_high),
        "stop": _round(stop),
        "tp1": _round(tp1),
        "tp2": _round(tp2),
        "trend": trend,
        "score": radar_score,
        "entry_score": entry_score,
        "risk_reward_tp1": _round(rr, 2),
        "distance_to_support_pct": _round(distance_to_support_pct, 2),
        "entry1": _round(entry1),
        "entry2": _round(entry2),
        "entry3": _round(entry3),
        "watch_price": _round(buy_high + min(atr * 0.30, last_close * 0.02)),
        "entry_allocations": [40, 35, 25],
        "action_code": action_code,
        "action_label": action_label,
        "action_class": action_class,
        "action_note": action_note,
        "show_entries": show_entries,
        "reasons": reasons[:5],
        "entry_reasons": entry_reasons[:4],
    }


def analyze_history(ticker):
    ticker = ticker.strip().upper()
    data = prepare_indicators(download_history(ticker, period="1y"))
    data.name = ticker
    result = build_snapshot(data)
    result["ticker"] = ticker
    return result


def backtest_ticker(ticker):
    """V3.3: validate signals and the proposed 3-step entry plan without look-ahead."""
    ticker = ticker.strip().upper()
    data = prepare_indicators(download_history(ticker, period="5y"))
    if len(data) < 140:
        raise ValueError("ข้อมูลย้อนหลังยังไม่พอสำหรับ Backtest ที่น่าเชื่อถือ")

    start = 70
    end = len(data) - 16
    signal_rows = []
    state_counts = {}
    previous_code = None

    for i in range(start, end):
        sub = data.iloc[: i + 1].copy()
        sub.name = ticker
        try:
            snap = build_snapshot(sub)
        except Exception:
            continue

        code = snap["action_code"]
        state_counts[code] = state_counts.get(code, 0) + 1

        # Count only a new state episode to avoid inflating samples with consecutive days.
        if code == previous_code:
            continue
        previous_code = code

        entry = safe_float(data.iloc[i]["Close"])
        if not entry or entry <= 0:
            continue

        returns = {}
        for horizon in (1, 3, 5, 10):
            future = safe_float(data.iloc[i + horizon]["Close"])
            returns[horizon] = ((future - entry) / entry * 100) if future else None

        window10 = data.iloc[i + 1 : i + 11]
        min_low = safe_float(window10["Low"].min())
        max_high = safe_float(window10["High"].max())
        mae10 = ((min_low - entry) / entry * 100) if min_low else None
        mfe10 = ((max_high - entry) / entry * 100) if max_high else None

        # Test whether each proposed limit-entry level was actually touched within 10 sessions.
        entry_tests = {}
        for n in (1, 2, 3):
            level = safe_float(snap.get(f"entry{n}"))
            hit = False
            fill_offset = None
            ret5_after_fill = None
            if level and level > 0:
                for off in range(1, 11):
                    row = data.iloc[i + off]
                    lo, hi = safe_float(row["Low"]), safe_float(row["High"])
                    if lo is not None and hi is not None and lo <= level <= hi:
                        hit, fill_offset = True, off
                        exit_idx = i + off + 5
                        if exit_idx < len(data):
                            exit_close = safe_float(data.iloc[exit_idx]["Close"])
                            if exit_close:
                                ret5_after_fill = (exit_close - level) / level * 100
                        break
            entry_tests[n] = {"hit": hit, "ret5": ret5_after_fill}

        signal_rows.append({
            "date": str(data.index[i])[:10],
            "action": code,
            "entry_score": snap["entry_score"],
            "radar_score": snap["score"],
            "r1": returns[1], "r3": returns[3], "r5": returns[5], "r10": returns[10],
            "mae10": mae10, "mfe10": mfe10,
            "e1_hit": entry_tests[1]["hit"], "e1_r5": entry_tests[1]["ret5"],
            "e2_hit": entry_tests[2]["hit"], "e2_r5": entry_tests[2]["ret5"],
            "e3_hit": entry_tests[3]["hit"], "e3_r5": entry_tests[3]["ret5"],
        })

    if not signal_rows:
        return {"ticker": ticker, "signals": 0, "message": "ยังไม่พบ episode ของสัญญาณที่ใช้วัดได้"}

    bt = pd.DataFrame(signal_rows)
    actionable = bt[bt["action"].isin(["ENTER", "SCALE"])].copy()

    def stat(frame, h):
        s = frame[f"r{h}"].dropna()
        if s.empty:
            return {"win_rate": None, "avg_return": None}
        return {"win_rate": round((s > 0).mean() * 100, 1), "avg_return": round(s.mean(), 2)}

    def entry_stat(n):
        hits = bt[f"e{n}_hit"]
        hit_count = int(hits.sum())
        total = int(len(hits))
        rets = bt.loc[hits, f"e{n}_r5"].dropna()
        return {
            "hit_rate": round(hit_count / total * 100, 1) if total else None,
            "hits": hit_count, "total": total,
            "win_rate_5d_after_fill": round((rets > 0).mean() * 100, 1) if not rets.empty else None,
            "avg_return_5d_after_fill": round(rets.mean(), 2) if not rets.empty else None,
        }

    r5 = actionable["r5"].dropna()
    gross_profit = r5[r5 > 0].sum()
    gross_loss = abs(r5[r5 < 0].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    sig_count = int(len(actionable))
    confidence = "High" if sig_count >= 50 else "Medium" if sig_count >= 20 else "Low"
    confidence_th = "สูง" if confidence == "High" else "ปานกลาง" if confidence == "Medium" else "ต่ำ"

    d0 = pd.Timestamp(data.index[0]).tz_localize(None) if getattr(pd.Timestamp(data.index[0]), 'tzinfo', None) else pd.Timestamp(data.index[0])
    d1 = pd.Timestamp(data.index[-1]).tz_localize(None) if getattr(pd.Timestamp(data.index[-1]), 'tzinfo', None) else pd.Timestamp(data.index[-1])
    years = round((d1 - d0).days / 365.25, 1)

    return {
        "ticker": ticker, "signals": sig_count, "episodes": int(len(bt)),
        "period_start": str(data.index[0])[:10], "period_end": str(data.index[-1])[:10],
        "actual_years": years, "confidence": confidence, "confidence_th": confidence_th,
        "d1": stat(actionable, 1), "d3": stat(actionable, 3),
        "d5": stat(actionable, 5), "d10": stat(actionable, 10),
        "profit_factor_5d": round(profit_factor, 2) if profit_factor is not None else None,
        "avg_mae_10d": round(actionable["mae10"].dropna().mean(), 2) if not actionable.empty else None,
        "avg_mfe_10d": round(actionable["mfe10"].dropna().mean(), 2) if not actionable.empty else None,
        "state_counts": state_counts,
        "entry1_test": entry_stat(1), "entry2_test": entry_stat(2), "entry3_test": entry_stat(3),
        "latest_signals": signal_rows[-5:][::-1],
        "method_note": "V3.3 นับผล ENTER/SCALE แบบ episode และทดสอบเพิ่มว่าไม้ 1/2/3 ถูกแตะจริงภายใน 10 วันทำการหรือไม่ จากนั้นวัดผล 5 วันหลังราคาแตะไม้ โดยไม่ใช้ข้อมูลอนาคตในการสร้างระดับราคา ไม่รวมค่าธรรมเนียม/Slippage",
    }


@app.route("/")
def home():
    return render_template(
        "index.html",
        events=load_json("events.json"),
        watchlist=load_json("watchlist.json"),
    )


@app.route("/api/history-analysis/<ticker>")
def history_analysis(ticker):
    try:
        data = analyze_history(ticker)
        return jsonify({"ok": True, "data": data}), 200
    except Exception as e:
        app.logger.error("history-analysis error for %s: %s", ticker, traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e) or "เกิดข้อผิดพลาดระหว่างวิเคราะห์ข้อมูล",
        }), 200


@app.route("/api/backtest/<ticker>")
def backtest(ticker):
    try:
        data = backtest_ticker(ticker)
        return jsonify({"ok": True, "data": data}), 200
    except Exception as e:
        app.logger.error("backtest error for %s: %s", ticker, traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e) or "เกิดข้อผิดพลาดระหว่าง Backtest",
        }), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "AI Market Radar", "version": "4.4.1"}), 200


@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "ไม่พบหน้า API ที่เรียก"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"ok": False, "error": "เซิร์ฟเวอร์มีปัญหาชั่วคราว กรุณาลองใหม่"}), 500



# Load scanner routes/UI extensions after the core app is fully defined.
# This registers Scanner APIs and swaps the home page to the Scanner dashboard.
try:
    import scanner  # noqa: F401
except Exception:
    app.logger.exception("Failed to load scanner module")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
