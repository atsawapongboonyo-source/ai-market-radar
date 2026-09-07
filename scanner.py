from flask import render_template, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app import app, load_json, analyze_history

# เก็บหน้า V3.4 เดิมไว้ที่ /analysis
_original_home = app.view_functions.get("home")
if _original_home:
    app.add_url_rule("/analysis", endpoint="analysis_v34", view_func=_original_home)

_SCAN_CACHE = {"ts": 0, "data": None}
_SCAN_TTL = 10 * 60


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

    # Ranking score = ใช้จัดลำดับเท่านั้น ไม่ใช่ % ความแม่นยำ
    rank_score = round(
        radar * 0.42 +
        entry * 0.48 +
        rr_bonus +
        action_bonus,
        1
    )

    return {
        "ticker": ticker,
        "last_close": d.get("last_close"),
        "trend": d.get("trend"),
        "radar_score": radar,
        "entry_score": entry,
        "rr": d.get("risk_reward_tp1"),
        "support": d.get("support"),
        "resistance": d.get("resistance"),
        "buy_low": d.get("buy_low"),
        "buy_high": d.get("buy_high"),
        "entry1": d.get("entry1"),
        "tp1": d.get("tp1"),
        "tp2": d.get("tp2"),
        "stop": d.get("stop"),
        "action_code": action,
        "action_label": d.get("action_label"),
        "action_class": d.get("action_class"),
        "action_note": d.get("action_note"),
        "watch_price": d.get("watch_price"),
        "data_date": d.get("data_date"),
        "rank_score": rank_score,
    }


def scan_watchlist(force=False):
    now = time.time()
    if (
        not force
        and _SCAN_CACHE["data"] is not None
        and now - _SCAN_CACHE["ts"] < _SCAN_TTL
    ):
        return _SCAN_CACHE["data"]

    watchlist = load_json("watchlist.json")
    tickers = [x["ticker"] for x in watchlist]

    results = []
    errors = []

    # จำกัด worker เพื่อไม่ยิงแหล่งข้อมูลฟรีแรงเกินไป
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_scan_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                errors.append({"ticker": ticker, "error": str(e)})

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

    counts = {}
    for r in results:
        counts[r["action_code"]] = counts.get(r["action_code"], 0) + 1

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "errors": errors,
        "counts": counts,
        "results": results,
        "note": "V3.5 Scanner ใช้ราคาปิดล่าสุดและข้อมูลย้อนหลังฟรีเพื่อคัดกรองก่อน จากนั้นใช้ราคาสดจาก Webull ตรวจจังหวะอีกครั้ง",
    }
    _SCAN_CACHE["ts"] = now
    _SCAN_CACHE["data"] = payload
    return payload


def scanner_home():
    return render_template(
        "scanner.html",
        watchlist=load_json("watchlist.json"),
    )


# เปลี่ยนหน้า / ให้เป็น Scanner V3.5 โดยเก็บ V3.4 ที่ /analysis
app.view_functions["home"] = scanner_home


@app.route("/scanner")
def scanner_page():
    return scanner_home()


@app.route("/api/scan")
def api_scan():
    try:
        return jsonify({"ok": True, "data": scan_watchlist(force=False)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/scan/refresh")
def api_scan_refresh():
    try:
        return jsonify({"ok": True, "data": scan_watchlist(force=True)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
