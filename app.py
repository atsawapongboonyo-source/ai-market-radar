from flask import Flask, render_template, jsonify
import json
from pathlib import Path
import math
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR))

def load_json(name):
    with (BASE_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)

def safe_float(v):
    try:
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_atr(df, period=14):
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        (df["High"] - df["Low"]).abs(),
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def analyze_history(ticker):
    data = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False
    )

    if data is None or data.empty:
        raise ValueError("ไม่พบข้อมูลย้อนหลัง")

    # yfinance บางรุ่นคืน MultiIndex columns
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    needed = ["Open", "High", "Low", "Close", "Volume"]
    for c in needed:
        if c not in data.columns:
            raise ValueError(f"ข้อมูล {c} ไม่ครบ")

    data = data.dropna(subset=["High", "Low", "Close"]).copy()
    if len(data) < 30:
        raise ValueError("ข้อมูลย้อนหลังไม่เพียงพอ")

    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
    data["EMA50"] = data["Close"].ewm(span=50, adjust=False).mean()
    data["RSI14"] = calc_rsi(data["Close"], 14)
    data["ATR14"] = calc_atr(data, 14)
    data["VOL20"] = data["Volume"].rolling(20).mean()

    last = data.iloc[-1]
    last_close = float(last["Close"])
    atr = safe_float(last["ATR14"]) or 0.0

    # แนวรับ/แนวต้านแบบโปร่งใส:
    # ใช้ low/high ของ 20 วันล่าสุด และ EMA20 เป็นตัวช่วย
    recent20 = data.tail(20)
    recent50 = data.tail(50)

    low20 = float(recent20["Low"].min())
    high20 = float(recent20["High"].max())
    low50 = float(recent50["Low"].min())
    high50 = float(recent50["High"].max())
    ema20 = safe_float(last["EMA20"])
    ema50 = safe_float(last["EMA50"])

    support_candidates = [low20]
    if ema20 and ema20 < last_close * 1.03:
        support_candidates.append(ema20)
    if ema50 and ema50 < last_close * 1.05:
        support_candidates.append(ema50)

    # เลือกแนวรับที่อยู่ใกล้ราคาปิดที่สุดแต่ไม่สูงเกินราคามาก
    support_candidates = [x for x in support_candidates if x and x <= last_close * 1.02]
    support = max(support_candidates) if support_candidates else low20

    resistance_candidates = [high20, high50]
    resistance_candidates = [x for x in resistance_candidates if x >= last_close * 0.98]
    resistance = min(resistance_candidates) if resistance_candidates else high20

    if resistance <= support:
        resistance = max(high20, last_close + max(atr, last_close * 0.03))

    buy_low = support
    buy_high = support + max(atr * 0.35, last_close * 0.004)
    buy_high = min(buy_high, resistance * 0.985)

    stop = max(0.01, support - max(atr * 0.5, last_close * 0.006))
    tp1 = resistance
    tp2 = resistance + max(atr * 0.5, last_close * 0.008)

    rsi = safe_float(last["RSI14"])
    vol = safe_float(last["Volume"])
    vol20 = safe_float(last["VOL20"])
    vol_ratio = (vol / vol20) if vol and vol20 and vol20 > 0 else None

    trend = "กลาง"
    if ema20 and ema50:
        if last_close > ema20 > ema50:
            trend = "ขาขึ้น"
        elif last_close < ema20 < ema50:
            trend = "ขาลง"

    score = 50
    reasons = []

    if trend == "ขาขึ้น":
        score += 15
        reasons.append("ราคาอยู่เหนือ EMA20 และ EMA50")
    elif trend == "ขาลง":
        score -= 15
        reasons.append("ราคาอยู่ต่ำกว่า EMA20 และ EMA50")
    else:
        reasons.append("แนวโน้มยังไม่ชัด")

    if rsi is not None:
        if 45 <= rsi <= 65:
            score += 8
            reasons.append("RSI อยู่ในโซนสมดุล")
        elif rsi > 72:
            score -= 8
            reasons.append("RSI ค่อนข้างร้อน")
        elif rsi < 35:
            score -= 4
            reasons.append("RSI อ่อนและต้องรอการยืนยัน")

    if vol_ratio is not None:
        if vol_ratio >= 1.2:
            score += 7
            reasons.append("Volume สูงกว่าค่าเฉลี่ย 20 วัน")
        elif vol_ratio < 0.7:
            score -= 3
            reasons.append("Volume เบากว่าปกติ")

    distance_to_support = (last_close - support) / last_close * 100
    if 0 <= distance_to_support <= 3:
        score += 10
        reasons.append("ราคาอยู่ไม่ไกลจากแนวรับ")
    elif distance_to_support > 8:
        score -= 6
        reasons.append("ราคาห่างแนวรับมาก ควรระวังการไล่ราคา")

    score = max(0, min(100, round(score)))

    return {
        "ticker": ticker.upper(),
        "data_date": data.index[-1].strftime("%Y-%m-%d"),
        "last_close": round(last_close, 2),
        "ema20": round(ema20, 2) if ema20 else None,
        "ema50": round(ema50, 2) if ema50 else None,
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "atr14": round(atr, 2),
        "volume_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "buy_low": round(buy_low, 2),
        "buy_high": round(buy_high, 2),
        "stop": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "trend": trend,
        "score": score,
        "reasons": reasons[:4]
    }

@app.route("/")
def home():
    return render_template(
        "index.html",
        events=load_json("events.json"),
        watchlist=load_json("watchlist.json")
    )

@app.route("/api/history-analysis/<ticker>")
def history_analysis(ticker):
    try:
        return jsonify({"ok": True, "data": analyze_history(ticker)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(load_json("watchlist.json"))

@app.route("/api/events")
def api_events():
    return jsonify(load_json("events.json"))

@app.route("/health")
def health():
    return jsonify({"status":"ok","service":"AI Market Radar","version":"3.0"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
