from flask import render_template, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app import app, load_json, analyze_history

# เก็บหน้า V3.4 เดิมไว้ที่ /analysis
_original_home = app.view_functions.get("home")
if _original_home:
    try:
        app.add_url_rule("/analysis", endpoint="analysis_v34", view_func=_original_home)
    except Exception:
        pass

_SCAN_CACHE = {"ts": 0, "data": None}
_SCAN_TTL = 10 * 60  # 10 นาที


def _scan_one(ticker):
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

    # Scanner = Candidate เท่านั้น จนกว่าจะผ่านราคาสด Webull
    if action in ("ENTER", "SCALE"):
        scanner_label = "🟦 Candidate — รอราคาสด"
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
    }


def _scan_with_retry(ticker, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return _scan_one(ticker), None, attempt
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                # หน่วงเพิ่มทีละนิดเพื่อลดปัญหา rate-limit
                time.sleep(0.55 * (attempt + 1))

    return None, {
        "ticker": ticker,
        "error": last_error or "ไม่ทราบสาเหตุ",
    }, retries


def scan_watchlist(force=False):
    now = time.time()

    if (
        not force
        and _SCAN_CACHE["data"] is not None
        and now - _SCAN_CACHE["ts"] < _SCAN_TTL
    ):
        cached = dict(_SCAN_CACHE["data"])
        cached["from_cache"] = True
        return cached

    watchlist = load_json("watchlist.json")
    tickers = [x["ticker"] for x in watchlist]

    results = []
    errors = []
    retry_success = 0

    # ลดจาก 4 เหลือ 2 worker เพื่อให้แหล่งข้อมูลฟรีมีโอกาสตอบครบมากขึ้น
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            executor.submit(_scan_with_retry, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(future_map):
            result, error, retry_count = future.result()

            if result:
                results.append(result)
                if retry_count > 0:
                    retry_success += 1
            elif error:
                errors.append(error)

    action_order = {
        "ENTER": 0,
        "SCALE": 1,
        "WAIT": 2,
        "DONT_CHASE": 3,
        "AVOID": 4,
    }

    results.sort(
        key=lambda x: (
            action_order.get(x["action_code"], 9),
            -x["rank_score"],
            -x["entry_score"],
        )
    )

    counts = {
        "CANDIDATE": 0,
        "WAIT": 0,
        "DONT_CHASE": 0,
        "AVOID": 0,
    }

    for r in results:
        if r["action_code"] in ("ENTER", "SCALE"):
            counts["CANDIDATE"] += 1
        else:
            counts[r["action_code"]] = counts.get(r["action_code"], 0) + 1

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "requested": len(tickers),
        "total": len(results),
        "failed": len(errors),
        "retry_success": retry_success,
        "errors": errors,
        "counts": counts,
        "results": results,
        "from_cache": False,
        "note": "V3.5.2 ลด concurrency และ retry หุ้นที่โหลดพลาดอัตโนมัติ",
    }

    _SCAN_CACHE["ts"] = now
    _SCAN_CACHE["data"] = payload
    return payload


def scanner_home():
    return render_template(
        "scanner.html",
        watchlist=load_json("watchlist.json"),
    )


# เปลี่ยนหน้าแรกให้เป็น Scanner
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
