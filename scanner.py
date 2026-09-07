from flask import render_template, jsonify, request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import time

from app import app, load_json, analyze_history

# เก็บหน้า V3.4 เดิมไว้ที่ /analysis
_original_home = app.view_functions.get("home")
if _original_home:
    try:
        app.add_url_rule("/analysis", endpoint="analysis_v34", view_func=_original_home)
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

_SCAN_CACHE = {"ts": 0, "data": None}
_SCAN_TTL = 10 * 60

_TICKER_CACHE_FILE = BASE_DIR / "scanner_cache.json"
_TICKER_CACHE_MAX_AGE = 3 * 24 * 60 * 60

_RECOVERY_WAIT_SECONDS = 1.4
_RECOVERY_RETRIES = 2


def _load_ticker_cache():
    try:
        if _TICKER_CACHE_FILE.exists():
            with _TICKER_CACHE_FILE.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return {}


def _save_ticker_cache(cache):
    try:
        with _TICKER_CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _build_scan_result(ticker):
    d = analyze_history(ticker)

    rr = d.get("risk_reward_tp1") or 0
    action = d.get("action_code", "WAIT")

    action_bonus = {
        "ENTER": 16,
        "SCALE": 12,
        "WAIT": 5,
        "DONT_CHASE": -2,
        "AVOID": -12,
    }.get(action, 0)

    radar = d.get("score") or 0
    entry = d.get("entry_score") or 0
    rr_bonus = min(max(rr, 0), 3) / 3 * 8

    raw_rank = radar * 0.42 + entry * 0.48 + rr_bonus + action_bonus
    rank_score = round(max(0, min(100, raw_rank)), 1)

    if action in ("ENTER", "SCALE"):
        scanner_label = "🟦 Candidate — รอ Confirmation"
        scanner_class = "candidate"
    elif action == "WAIT":
        scanner_label = "🟡 รอจังหวะ"
        scanner_class = "wait"
    elif action == "DONT_CHASE":
        scanner_label = "🟠 ไม่ไล่ราคา"
        scanner_class = "chase"
    else:
        scanner_label = "🔴 ยังไม่เข้า"
        scanner_class = "avoid"

    return {
        "ticker": ticker,
        "last_close": d.get("last_close"),
        "radar_score": radar,
        "entry_score": entry,
        "rr": d.get("risk_reward_tp1"),
        "buy_low": d.get("buy_low"),
        "buy_high": d.get("buy_high"),
        "entry1": d.get("entry1"),
        "tp1": d.get("tp1"),
        "tp2": d.get("tp2"),
        "stop": d.get("stop"),
        "action_code": action,
        "scanner_label": scanner_label,
        "scanner_class": scanner_class,
        "rank_score": rank_score,
        "data_date": d.get("data_date"),
        "freshness": "fresh",
        "freshness_label": "🟢 Fresh",
        "confidence_code": "FRESH",
        "confidence_score": 100,
        "cache_age_minutes": 0,
    }


def _initial_scan_with_retry(ticker, retries=2):
    last_error = None

    for attempt in range(retries + 1):
        try:
            result = _build_scan_result(ticker)
            return result, None, attempt
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                time.sleep(0.75 * (attempt + 1))

    return None, {"ticker": ticker, "error": last_error or "ไม่ทราบสาเหตุ"}, retries


def _recovery_scan_one(ticker):
    last_error = None

    for attempt in range(_RECOVERY_RETRIES + 1):
        try:
            if attempt > 0:
                time.sleep(_RECOVERY_WAIT_SECONDS * attempt)

            result = _build_scan_result(ticker)
            result["freshness"] = "recovered"
            result["freshness_label"] = "🟡 Recovered"
            result["confidence_code"] = "RECOVERED"
            result["confidence_score"] = 85
            return result, None

        except Exception as e:
            last_error = str(e)

    return None, {"ticker": ticker, "error": last_error or "Recovery ล้มเหลว"}


def _cached_result_for(ticker, cache, now):
    item = cache.get(ticker)

    if not isinstance(item, dict):
        return None

    saved_at = item.get("_saved_at")
    data = item.get("data")

    if not saved_at or not isinstance(data, dict):
        return None

    age = now - float(saved_at)

    if age < 0 or age > _TICKER_CACHE_MAX_AGE:
        return None

    result = dict(data)

    result["freshness"] = "cached"
    result["freshness_label"] = "⚪ Cached"
    result["confidence_code"] = "CACHED"

    age_hours = age / 3600

    if age_hours <= 24:
        confidence = 70
    elif age_hours <= 48:
        confidence = 55
    else:
        confidence = 40

    result["confidence_score"] = confidence
    result["cache_age_minutes"] = round(age / 60, 1)

    if result.get("action_code") in ("ENTER", "SCALE"):
        result["scanner_label"] = "⚪ Candidate จาก Cache — ห้ามใช้เข้าโดยตรง"
        result["scanner_class"] = "cached"

    return result


def scan_watchlist(force=False):
    now = time.time()

    if (
        not force
        and _SCAN_CACHE["data"] is not None
        and now - _SCAN_CACHE["ts"] < _SCAN_TTL
    ):
        cached_page = dict(_SCAN_CACHE["data"])
        cached_page["from_cache"] = True
        return cached_page

    watchlist = load_json("watchlist.json")
    tickers = [x["ticker"] for x in watchlist]
    ticker_cache = _load_ticker_cache()

    fresh_results = []
    recovered_results = []
    cached_results = []
    final_errors = []

    initial_failed_tickers = []
    initial_error_map = {}
    initial_retry_success = 0

    # Stage 1: Initial Scan
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            executor.submit(_initial_scan_with_retry, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(future_map):
            ticker = future_map[future]
            result, error, retry_count = future.result()

            if result:
                fresh_results.append(result)

                if retry_count > 0:
                    initial_retry_success += 1

                ticker_cache[ticker] = {
                    "_saved_at": now,
                    "data": result,
                }

            else:
                initial_failed_tickers.append(ticker)
                initial_error_map[ticker] = error

    # Stage 2: Recovery Queue
    for ticker in initial_failed_tickers:
        time.sleep(_RECOVERY_WAIT_SECONDS)

        recovered, recovery_error = _recovery_scan_one(ticker)

        if recovered:
            recovered_results.append(recovered)
            ticker_cache[ticker] = {
                "_saved_at": now,
                "data": recovered,
            }

        else:
            # Stage 3: Cache fallback
            fallback = _cached_result_for(ticker, ticker_cache, now)

            if fallback:
                cached_results.append(fallback)
            else:
                final_errors.append(
                    recovery_error
                    or initial_error_map.get(ticker)
                    or {"ticker": ticker, "error": "ไม่มีข้อมูล"}
                )

    _save_ticker_cache(ticker_cache)

    final_results = fresh_results + recovered_results + cached_results

    action_order = {
        "ENTER": 0,
        "SCALE": 1,
        "WAIT": 2,
        "DONT_CHASE": 3,
        "AVOID": 4,
    }

    confidence_order = {
        "FRESH": 0,
        "RECOVERED": 1,
        "CACHED": 2,
    }

    final_results.sort(
        key=lambda x: (
            confidence_order.get(x.get("confidence_code"), 9),
            action_order.get(x.get("action_code"), 9),
            -float(x.get("rank_score") or 0),
            -float(x.get("entry_score") or 0),
        )
    )

    counts = {
        "CANDIDATE": 0,
        "WAIT": 0,
        "DONT_CHASE": 0,
        "AVOID": 0,
        "FRESH": len(fresh_results),
        "RECOVERED": len(recovered_results),
        "CACHED": len(cached_results),
        "MISSING": len(final_errors),
    }

    for r in final_results:
        if r.get("action_code") in ("ENTER", "SCALE"):
            counts["CANDIDATE"] += 1
        else:
            code = r.get("action_code", "WAIT")
            counts[code] = counts.get(code, 0) + 1

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "requested": len(tickers),
        "total": len(final_results),
        "fresh_count": len(fresh_results),
        "recovered_count": len(recovered_results),
        "fallback_used": len(cached_results),
        "failed": len(final_errors),
        "initial_failed": len(initial_failed_tickers),
        "retry_success": initial_retry_success,
        "errors": final_errors,
        "counts": counts,
        "results": final_results,
        "from_cache": False,
        "note": "V3.6: Scanner + Recovery + Data Confidence + Market Confirmation",
    }

    _SCAN_CACHE["ts"] = now
    _SCAN_CACHE["data"] = payload

    return payload


def _clamp(v, low=0, high=100):
    return max(low, min(high, v))


def _market_confirmation(payload):
    """
    Confirmation Score = คะแนนเงื่อนไข ไม่ใช่เปอร์เซ็นต์โอกาสชนะ
    ใช้ข้อมูลจาก Webull/สิ่งที่ผู้ใช้เห็นตอนนั้น:
    - ราคาปัจจุบัน
    - QQQ
    - Sector/AI group
    - Relative Volume
    - News/Catalyst
    """
    price = float(payload.get("price"))
    buy_low = float(payload.get("buy_low"))
    buy_high = float(payload.get("buy_high"))
    stop = float(payload.get("stop"))
    tp1 = float(payload.get("tp1"))

    data_confidence = payload.get("data_confidence", "FRESH")
    qqq = payload.get("qqq", "neutral")
    sector = payload.get("sector", "neutral")
    news = payload.get("news", "neutral")

    volume_ratio = float(payload.get("volume_ratio") or 1.0)

    if data_confidence == "CACHED":
        return {
            "status": "BLOCK",
            "score": 0,
            "label": "🔴 ไม่อนุญาต",
            "reason": "ข้อมูล Scanner เป็น Cached ต้องรีเฟรชข้อมูลใหม่ก่อน",
            "checks": [],
        }

    checks = []
    score = 50

    # 1. Price validation
    if price < stop:
        return {
            "status": "BLOCK",
            "score": 0,
            "label": "🔴 ไม่เข้า",
            "reason": "ราคาหลุด Stop / Invalidation",
            "checks": ["🔴 ราคาไม่ผ่าน"],
        }

    if price < buy_low:
        checks.append("🟡 ราคาต่ำกว่า Buy Zone")
        price_score = -10
    elif buy_low <= price <= buy_high:
        checks.append("🟢 ราคาอยู่ใน Buy Zone")
        price_score = 18
    elif price < tp1:
        checks.append("🟠 ราคาเหนือ Buy Zone")
        price_score = -6
    else:
        return {
            "status": "BLOCK",
            "score": 10,
            "label": "🔴 ไม่เข้าใหม่",
            "reason": "ราคาแตะหรือสูงกว่า TP1 แล้ว",
            "checks": ["🔴 Risk/Reward สำหรับจุดเข้าใหม่ลดลง"],
        }

    score += price_score

    # 2. QQQ / Market
    qqq_score = {
        "bull": 12,
        "neutral": 0,
        "bear": -16,
    }.get(qqq, 0)

    score += qqq_score

    checks.append({
        "bull": "🟢 QQQ/ตลาดเป็นบวก",
        "neutral": "⚪ QQQ/ตลาดกลาง",
        "bear": "🔴 QQQ/ตลาดเป็นลบ",
    }.get(qqq, "⚪ QQQ/ตลาดกลาง"))

    # 3. Sector / AI group
    sector_score = {
        "bull": 10,
        "neutral": 0,
        "bear": -13,
    }.get(sector, 0)

    score += sector_score

    checks.append({
        "bull": "🟢 กลุ่มหุ้นแข็งกว่าตลาด",
        "neutral": "⚪ กลุ่มหุ้นกลาง",
        "bear": "🔴 กลุ่มหุ้นอ่อน",
    }.get(sector, "⚪ กลุ่มหุ้นกลาง"))

    # 4. Relative volume
    if volume_ratio >= 1.50:
        score += 12
        checks.append(f"🟢 Volume สูง {volume_ratio:.2f}x")
    elif volume_ratio >= 1.10:
        score += 6
        checks.append(f"🟢 Volume สนับสนุน {volume_ratio:.2f}x")
    elif volume_ratio >= 0.80:
        checks.append(f"⚪ Volume ปกติ {volume_ratio:.2f}x")
    else:
        score -= 10
        checks.append(f"🟠 Volume เบา {volume_ratio:.2f}x")

    # 5. News / Catalyst
    news_score = {
        "positive": 10,
        "neutral": 0,
        "negative": -25,
    }.get(news, 0)

    score += news_score

    checks.append({
        "positive": "🟢 ข่าว/Catalyst เป็นบวก",
        "neutral": "⚪ ไม่มีข่าวสำคัญ/กลาง",
        "negative": "🔴 ข่าว/Catalyst เป็นลบ",
    }.get(news, "⚪ ไม่มีข่าวสำคัญ/กลาง"))

    score = round(_clamp(score))

    # Hard market blocks
    if news == "negative":
        status = "BLOCK"
        label = "🔴 ไม่เข้า"
        reason = "ข่าว/Catalyst ลบ — รอให้ตลาดย่อยข่าวก่อน"

    elif qqq == "bear" and sector == "bear":
        status = "BLOCK"
        label = "🔴 ไม่เข้า"
        reason = "ตลาดรวมและกลุ่มหุ้นเป็นลบพร้อมกัน"

    elif price < buy_low:
        status = "WAIT"
        label = "🟡 รอ"
        reason = "ราคายังต่ำกว่า Buy Zone แม้ Context อื่นอาจดี"

    elif price > buy_high:
        status = "WAIT"
        label = "🟠 รอ Pullback"
        reason = "ราคาเหนือ Buy Zone — ไม่ไล่ราคา"

    elif score >= 78:
        status = "CONFIRMED"
        label = "🟢 Confirmed"
        reason = "ราคา + ตลาด + กลุ่ม + Volume/ข่าว ผ่านในระดับดี"

    elif score >= 62:
        status = "CAUTION"
        label = "🟡 ผ่านแบบระวัง"
        reason = "ราคาอยู่ในโซน แต่ Market Confirmation ยังไม่เต็ม"

    else:
        status = "WAIT"
        label = "🟡 รอ"
        reason = "Confirmation ยังไม่พอสำหรับเข้าไม้ 1"

    return {
        "status": status,
        "score": score,
        "label": label,
        "reason": reason,
        "checks": checks,
    }


def scanner_home():
    return render_template(
        "scanner.html",
        watchlist=load_json("watchlist.json"),
    )


app.view_functions["home"] = scanner_home


@app.route("/scanner")
def scanner_page():
    return scanner_home()


@app.route("/api/scan")
def api_scan():
    try:
        return jsonify({"ok": True, "data": scan_watchlist(False)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/scan/refresh")
def api_scan_refresh():
    try:
        return jsonify({"ok": True, "data": scan_watchlist(True)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/market-confirm", methods=["POST"])
def market_confirm():
    try:
        payload = request.get_json(silent=True) or {}
        result = _market_confirmation(payload)
        return jsonify({"ok": True, "data": result}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
