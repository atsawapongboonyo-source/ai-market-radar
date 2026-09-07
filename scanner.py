from flask import render_template, jsonify, request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json, time

from app import app, load_json, analyze_history

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

# กลุ่มสำหรับวัด breadth/sector context จากผลสแกนชุดเดียวกัน (ฟรี)
GROUPS = {
    "chip": {"NVDA","AMD","AVGO","TSM","ASML","AMAT","LRCX","KLAC"},
    "memory": {"MU","SNDK","WDC","STX"},
    "network": {"ANET","MRVL","CRDO","LITE","COHR"},
    "datacenter": {"VRT","DELL","SMCI","NBIS","IREN"},
    "power": {"ETN","GEV","CEG","VST"},
    "cloud": {"MSFT","GOOGL","AMZN","ORCL","META"},
    "software": {"PLTR"},
}

def _group_for(ticker):
    for name, tickers in GROUPS.items():
        if ticker in tickers:
            return name
    return "other"

def _load_ticker_cache():
    try:
        if _TICKER_CACHE_FILE.exists():
            with _TICKER_CACHE_FILE.open("r", encoding="utf-8") as f:
                x=json.load(f)
            return x if isinstance(x,dict) else {}
    except Exception:
        pass
    return {}

def _save_ticker_cache(cache):
    try:
        with _TICKER_CACHE_FILE.open("w",encoding="utf-8") as f:
            json.dump(cache,f,ensure_ascii=False,indent=2)
    except Exception:
        pass

def _build(ticker):
    d=analyze_history(ticker)
    rr=d.get("risk_reward_tp1") or 0
    action=d.get("action_code","WAIT")
    radar=d.get("score") or 0
    entry=d.get("entry_score") or 0
    bonus={"ENTER":16,"SCALE":12,"WAIT":5,"DONT_CHASE":-2,"AVOID":-12}.get(action,0)
    rr_bonus=min(max(rr,0),3)/3*8
    rank=round(max(0,min(100,radar*.42+entry*.48+rr_bonus+bonus)),1)
    labels={
      "ENTER":("🟦 Candidate — รอราคาสด","candidate"),
      "SCALE":("🟦 Candidate — รอราคาสด","candidate"),
      "WAIT":("🟡 รอจังหวะ","wait"),
      "DONT_CHASE":("🟠 ไม่ไล่ราคา","chase"),
      "AVOID":("🔴 ยังไม่เข้า","avoid")
    }
    label,cls=labels.get(action,labels["WAIT"])
    return {
      "ticker":ticker,"last_close":d.get("last_close"),
      "radar_score":radar,"entry_score":entry,"rr":d.get("risk_reward_tp1"),
      "buy_low":d.get("buy_low"),"buy_high":d.get("buy_high"),
      "entry1":d.get("entry1"),"tp1":d.get("tp1"),"tp2":d.get("tp2"),
      "stop":d.get("stop"),"action_code":action,
      "scanner_label":label,"scanner_class":cls,"rank_score":rank,
      "data_date":d.get("data_date"),"group":_group_for(ticker),
      "confidence_code":"FRESH","confidence_score":100,
      "freshness_label":"🟢 Fresh"
    }

def _try(ticker,retries=2):
    err=None
    for i in range(retries+1):
        try:return _build(ticker),None,i
        except Exception as e:
            err=str(e)
            if i<retries: time.sleep(.75*(i+1))
    return None,{"ticker":ticker,"error":err or "unknown"},retries

def _cached(ticker,cache,now):
    item=cache.get(ticker)
    if not isinstance(item,dict): return None
    saved=item.get("_saved_at"); data=item.get("data")
    if not saved or not isinstance(data,dict): return None
    age=now-float(saved)
    if age<0 or age>_TICKER_CACHE_MAX_AGE:return None
    r=dict(data)
    r["confidence_code"]="CACHED"
    r["confidence_score"]=70 if age<=86400 else 55 if age<=172800 else 40
    r["freshness_label"]="⚪ Cached"
    r["scanner_label"]="⚪ Cache — ต้องยืนยันข้อมูลใหม่"
    r["scanner_class"]="cached"
    return r

def _derive_context(results):
    """ใช้ breadth ของ watchlist เป็น market/sector proxy โดยไม่อ้างว่าเป็นราคาสด QQQ"""
    usable=[x for x in results if x.get("confidence_code")!="CACHED"]
    if not usable:return {"market":"unknown","market_score":0,"groups":{}}

    def strength(items):
        if not items:return 0
        vals=[]
        for x in items:
            a=x.get("action_code")
            vals.append({"ENTER":1,"SCALE":.8,"WAIT":0,"DONT_CHASE":-.35,"AVOID":-1}.get(a,0))
        return sum(vals)/len(vals)

    all_s=strength(usable)
    market="bull" if all_s>=.22 else "bear" if all_s<=-.22 else "neutral"
    gs={}
    for g in GROUPS:
        members=[x for x in usable if x.get("group")==g]
        s=strength(members)
        gs[g]={
          "state":"bull" if s>=.25 else "bear" if s<=-.25 else "neutral",
          "strength":round(s,2),"count":len(members)
        }
    return {"market":market,"market_score":round(all_s,2),"groups":gs}

def scan_watchlist(force=False):
    now=time.time()
    if not force and _SCAN_CACHE["data"] and now-_SCAN_CACHE["ts"]<_SCAN_TTL:
        x=dict(_SCAN_CACHE["data"]);x["from_cache"]=True;return x

    tickers=[x["ticker"] for x in load_json("watchlist.json")]
    cache=_load_ticker_cache()
    fresh=[]; recovered=[]; cached=[]; errors=[]; failed=[]

    with ThreadPoolExecutor(max_workers=2) as ex:
        fs={ex.submit(_try,t):t for t in tickers}
        for f in as_completed(fs):
            t=fs[f];r,e,n=f.result()
            if r:
                fresh.append(r);cache[t]={"_saved_at":now,"data":r}
            else: failed.append((t,e))

    # Recovery queue แบบทีละตัว
    for t,e in failed:
        time.sleep(1.2)
        r,e2,n=_try(t,1)
        if r:
            r["confidence_code"]="RECOVERED";r["confidence_score"]=85
            r["freshness_label"]="🟡 Recovered";recovered.append(r)
            cache[t]={"_saved_at":now,"data":r}
        else:
            c=_cached(t,cache,now)
            if c: cached.append(c)
            else: errors.append(e2 or e)

    _save_ticker_cache(cache)
    results=fresh+recovered+cached
    ctx=_derive_context(results)

    order={"ENTER":0,"SCALE":1,"WAIT":2,"DONT_CHASE":3,"AVOID":4}
    conf={"FRESH":0,"RECOVERED":1,"CACHED":2}
    results.sort(key=lambda x:(conf.get(x["confidence_code"],9),
                               order.get(x["action_code"],9),
                               -x["rank_score"]))

    payload={
      "updated_at":time.strftime("%Y-%m-%d %H:%M:%S"),
      "requested":len(tickers),"total":len(results),"failed":len(errors),
      "fresh_count":len(fresh),"recovered_count":len(recovered),
      "fallback_used":len(cached),"errors":errors,"results":results,
      "auto_context":ctx,"from_cache":False,
      "note":"V3.7 Auto Context: watchlist breadth + sector breadth; live price remains manual"
    }
    _SCAN_CACHE.update({"ts":now,"data":payload})
    return payload

def _clamp(x):return max(0,min(100,x))

def _auto_confirm(p):
    price=float(p["price"]); lo=float(p["buy_low"]); hi=float(p["buy_high"])
    stop=float(p["stop"]);tp1=float(p["tp1"])
    confidence=p.get("data_confidence","FRESH")
    market=p.get("market","unknown"); sector=p.get("sector","unknown")

    if confidence=="CACHED":
        return {"status":"BLOCK","score":0,"label":"🔴 ยังไม่เข้า",
                "reason":"ข้อมูลหุ้นเป็น Cache ต้องรีเฟรชก่อน","checks":[]}
    if price<stop:
        return {"status":"BLOCK","score":0,"label":"🔴 ยังไม่เข้า",
                "reason":"ราคาหลุดจุดแผนผิด","checks":["🔴 ราคาไม่ผ่าน"]}
    if price>=tp1:
        return {"status":"BLOCK","score":10,"label":"🔴 ไม่ไล่ราคา",
                "reason":"ราคาถึง/เกิน TP1 แล้ว","checks":["🔴 Risk/Reward ไม่เหมาะกับการเข้าใหม่"]}

    score=50;checks=[]
    if lo<=price<=hi:
        score+=22;checks.append("🟢 ราคาอยู่ใน Buy Zone")
    elif price<lo:
        score-=8;checks.append("🟡 ราคาต่ำกว่า Buy Zone — รอการยืนยัน")
    else:
        score-=10;checks.append("🟠 ราคาเหนือ Buy Zone — ไม่ควรไล่")

    if market=="bull":
        score+=10;checks.append("🟢 Watchlist breadth โดยรวมแข็งแรง")
    elif market=="bear":
        score-=14;checks.append("🔴 Watchlist breadth โดยรวมอ่อน")
    elif market=="neutral":
        checks.append("⚪ Watchlist breadth กลาง")
    else: checks.append("⚪ Market context ยังไม่พอ")

    if sector=="bull":
        score+=10;checks.append("🟢 หุ้นกลุ่มเดียวกันแข็งแรง")
    elif sector=="bear":
        score-=14;checks.append("🔴 หุ้นกลุ่มเดียวกันอ่อน")
    elif sector=="neutral":
        checks.append("⚪ กลุ่มหุ้นกลาง")
    else: checks.append("⚪ ข้อมูลกลุ่มยังไม่พอ")

    score=round(_clamp(score))

    if market=="bear" and sector=="bear":
        status,label,reason="BLOCK","🔴 ยังไม่เข้า","ตลาดที่สแกนและกลุ่มหุ้นอ่อนพร้อมกัน"
    elif price>hi:
        status,label,reason="WAIT","🟠 ไม่ไล่ราคา","ราคาเหนือ Buy Zone"
    elif price<lo:
        status,label,reason="WAIT","🟡 รอจังหวะ","ราคายังไม่กลับเข้า Buy Zone"
    elif score>=80:
        status,label,reason="CONFIRMED","🟢 เข้าไม้ 1 ได้","ราคาและ Auto Context ผ่าน"
    elif score>=64:
        status,label,reason="CAUTION","🟡 ผ่านแบบระวัง","ราคาอยู่ในโซน แต่ Context ยังไม่เต็ม"
    else:
        status,label,reason="WAIT","🟡 รอก่อน","Auto Context ยังไม่แข็งแรงพอ"

    return {"status":status,"score":score,"label":label,"reason":reason,"checks":checks}

def scanner_home():
    return render_template("scanner.html",watchlist=load_json("watchlist.json"))

app.view_functions["home"]=scanner_home

@app.route("/scanner")
def scanner_page():return scanner_home()

@app.route("/api/scan")
def api_scan():
    try:return jsonify({"ok":True,"data":scan_watchlist(False)}),200
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),200

@app.route("/api/scan/refresh")
def api_scan_refresh():
    try:return jsonify({"ok":True,"data":scan_watchlist(True)}),200
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),200

@app.route("/api/auto-confirm",methods=["POST"])
def auto_confirm():
    try:return jsonify({"ok":True,"data":_auto_confirm(request.get_json(silent=True) or {})}),200
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=False)
