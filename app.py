from flask import Flask, render_template, jsonify
import json
from pathlib import Path
import traceback
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR))

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
        # yfinance อาจคืน ('Close','SNDK') หรือ ('SNDK','Close')
        level0 = list(df.columns.get_level_values(0))
        level1 = list(df.columns.get_level_values(1))
        price_names = {"Open","High","Low","Close","Adj Close","Volume"}
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
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))

def calc_atr(df, period=14):
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        (df["High"] - df["Low"]).abs(),
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def download_history(ticker):
    ticker = ticker.strip().upper()

    # ลอง download ก่อน
    try:
        data = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=12
        )
        data = flatten_columns(data)
        if data is not None and not data.empty:
            return data
    except Exception:
        pass

    # fallback ผ่าน Ticker.history
    try:
        data = yf.Ticker(ticker).history(
            period="6mo",
            interval="1d",
            auto_adjust=False,
            timeout=12
        )
        data = flatten_columns(data)
        if data is not None and not data.empty:
            return data
    except TypeError:
        # บางเวอร์ชันไม่รับ timeout ใน history
        data = yf.Ticker(ticker).history(
            period="6mo",
            interval="1d",
            auto_adjust=False
        )
        data = flatten_columns(data)
        if data is not None and not data.empty:
            return data

    raise ValueError("แหล่งข้อมูลฟรีไม่ตอบกลับหรือไม่พบข้อมูลหุ้นนี้ กรุณาลองอีกครั้งในอีกสักครู่")

def analyze_history(ticker):
    data = download_history(ticker)

    needed = ["High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in data.columns]
    if missing:
        raise ValueError("ข้อมูลย้อนหลังไม่ครบ: " + ", ".join(missing))

    data = data.dropna(subset=["High", "Low", "Close"]).copy()
    if len(data) < 30:
        raise ValueError("ข้อมูลย้อนหลังไม่เพียงพอสำหรับการคำนวณ")

    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
    data["EMA50"] = data["Close"].ewm(span=50, adjust=False).mean()
    data["RSI14"] = calc_rsi(data["Close"], 14)
    data["ATR14"] = calc_atr(data, 14)
    data["VOL20"] = data["Volume"].rolling(20).mean()

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
        resistance * 0.985
    )
    if buy_high < buy_low:
        buy_high = buy_low + max(atr * 0.2, last_close * 0.003)

    stop = max(0.01, support - max(atr * 0.5, last_close * 0.006))
    tp1 = resistance
    tp2 = resistance + max(atr * 0.5, last_close * 0.008)

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
        reasons.append("แนวโน้ม EMA ยังไม่ชัด")

    if rsi is not None:
        if 45 <= rsi <= 65:
            score += 8
            reasons.append("RSI อยู่ในโซนสมดุล")
        elif rsi > 72:
            score -= 8
            reasons.append("RSI ค่อนข้างร้อน")
        elif rsi < 35:
            score -= 4
            reasons.append("RSI อ่อน ควรรอการยืนยัน")

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
        reasons.append("ราคาห่างแนวรับมาก ระวังการไล่ราคา")

    score = max(0, min(100, round(score)))

    idx = data.index[-1]
    try:
        data_date = idx.strftime("%Y-%m-%d")
    except Exception:
        data_date = str(idx)[:10]

    return {
        "ticker": ticker.upper(),
        "data_date": data_date,
        "last_close": round(last_close, 2),
        "ema20": round(ema20, 2) if ema20 is not None else None,
        "ema50": round(ema50, 2) if ema50 is not None else None,
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
        data = analyze_history(ticker)
        return jsonify({"ok": True, "data": data}), 200
    except Exception as e:
        # สำคัญ: route นี้ส่ง JSON กลับเสมอ แม้เกิด error
        app.logger.error("history-analysis error for %s: %s", ticker, traceback.format_exc())
        return jsonify({
            "ok": False,
            "error": str(e) or "เกิดข้อผิดพลาดระหว่างวิเคราะห์ข้อมูล"
        }), 200

@app.route("/health")
def health():
    return jsonify({"status":"ok","service":"AI Market Radar","version":"3.1"}), 200

@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "ไม่พบหน้า API ที่เรียก"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"ok": False, "error": "เซิร์ฟเวอร์มีปัญหาชั่วคราว กรุณาลองใหม่"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
