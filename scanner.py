from flask import render_template, jsonify, request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
import json, time
import yfinance as yf

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

_CATALYST_CACHE = {}
_CATALYST_TTL = 15 * 60

_TOP_PICK_CACHE = {"ts": 0, "data": None}
_TOP_PICK_TTL = 10 * 60
_TOP_PICK_NEWS_LIMIT = 5

POSITIVE_WORDS = ("beat","beats","raises","upgrade","record","growth","surge","strong","contract","deal","partnership","wins","launch","expands","demand","order","outperform")
NEGATIVE_WORDS = ("miss","misses","cuts","downgrade","probe","lawsuit","warning","weak","decline","falls","delay","recall","investigation","underperform")
HIGH_IMPACT_WORDS = ("earnings","guidance","revenue","profit","contract","deal","partnership","upgrade","downgrade","investigation","lawsuit","order","forecast","outlook")

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
      "note":"V4.2 Premarket Gate: calibrated top picks + manual Webull premarket confirmation + catalyst + final decision"
    }
    _SCAN_CACHE.update({"ts":now,"data":payload})
    return payload


def _news_fields(item):
    if not isinstance(item, dict): return None
    c = item.get("content") if isinstance(item.get("content"), dict) else item
    title = c.get("title") or c.get("headline") or item.get("title") or ""
    provider = c.get("provider")
    publisher = (provider.get("displayName") or provider.get("name") or "") if isinstance(provider,dict) else (c.get("publisher") or item.get("publisher") or "")
    link = ""
    for key in ("canonicalUrl","clickThroughUrl"):
        v=c.get(key)
        if isinstance(v,dict) and v.get("url"): link=v["url"]; break
    link = link or item.get("link") or c.get("link") or ""
    published = c.get("pubDate") or c.get("displayTime") or item.get("providerPublishTime")
    return {"title":str(title).strip(),"publisher":str(publisher).strip(),"link":str(link).strip(),"published":published}

def _age_hours(v):
    try:
        if v is None:return None
        if isinstance(v,(int,float)): dt=datetime.fromtimestamp(v,tz=timezone.utc)
        else:
            dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return max(0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/3600)
    except Exception:return None

def _classify_title(title):
    t=title.lower()
    pos=sum(1 for w in POSITIVE_WORDS if w in t)
    neg=sum(1 for w in NEGATIVE_WORDS if w in t)
    high=any(w in t for w in HIGH_IMPACT_WORDS)
    return ("negative",-1,high) if neg>pos else ("positive",1,high) if pos>neg else ("neutral",0,high)

def _get_catalyst(ticker, force=False):
    now=time.time()
    hit=_CATALYST_CACHE.get(ticker)
    if hit and not force and now-hit["ts"]<_CATALYST_TTL:
        d=dict(hit["data"]); d["from_cache"]=True; return d
    try:
        raw=yf.Ticker(ticker).news or []
    except Exception as e:
        return {"ticker":ticker,"score":50,"sentiment":"unknown","label":"⚪ ข่าวยังไม่พร้อม","reason":"แหล่งข่าวฟรีไม่ตอบกลับ","items":[],"negative_high_impact":False,"error":str(e)}
    items=[]; weighted=0; total=0; neg_high=False
    for raw_item in raw[:12]:
        x=_news_fields(raw_item)
        if not x or not x["title"]: continue
        sent,base,high=_classify_title(x["title"]); age=_age_hours(x["published"])
        rw=1.0 if age is not None and age<=24 else .7 if age is not None and age<=72 else .4 if age is not None and age<=168 else .2
        w=rw*(1.35 if high else 1); weighted+=base*w; total+=w
        if sent=="negative" and high and (age is None or age<=72): neg_high=True
        x.update({"sentiment":sent,"high_impact":high,"age_hours":round(age,1) if age is not None else None})
        items.append(x)
        if len(items)>=6: break
    if not items:
        data={"ticker":ticker,"score":50,"sentiment":"neutral","label":"⚪ ยังไม่พบ Catalyst ชัด","reason":"ไม่พบหัวข้อข่าวจากแหล่งฟรี","items":[],"negative_high_impact":False}
    else:
        ratio=weighted/total if total else 0; score=round(max(0,min(100,50+ratio*28)))
        if neg_high: sent,label,reason="negative","🔴 มี Risk Catalyst","พบข่าวลบ Impact สูงในช่วงล่าสุด"
        elif score>=63: sent,label,reason="positive","🟢 Positive Catalyst","หัวข้อข่าวล่าสุดมีน้ำหนักเชิงบวก"
        elif score<=37: sent,label,reason="negative","🔴 Negative Catalyst","หัวข้อข่าวล่าสุดมีน้ำหนักเชิงลบ"
        else: sent,label,reason="neutral","⚪ Catalyst กลาง","ข่าวล่าสุดยังไม่ให้ทิศทางชัด"
        data={"ticker":ticker,"score":score,"sentiment":sent,"label":label,"reason":reason,"items":items,"negative_high_impact":neg_high}
    _CATALYST_CACHE[ticker]={"ts":now,"data":data}
    return data


def _freshness_bonus(code):
    return {"FRESH": 8, "RECOVERED": 3, "CACHED": -18}.get(code, -10)


def _context_bonus(state):
    return {"bull": 8, "neutral": 0, "bear": -10, "unknown": -4}.get(state, -4)


def _catalyst_bonus(cat):
    sent = cat.get("sentiment", "unknown")
    score = float(cat.get("score") or 50)

    if cat.get("negative_high_impact"):
        return -28

    if sent == "positive":
        return min(12, max(4, (score - 50) * 0.35))
    if sent == "negative":
        return -min(20, max(8, (50 - score) * 0.45))
    if sent == "neutral":
        return 0
    return -3


def _top_pick_score(item, ctx, catalyst):
    """
    V4.1 calibrated Watch Score.
    This is a priority/confidence score, NOT win probability and NOT a buy signal.
    Designed to avoid 98-100 saturation and make differences meaningful.
    """
    rr = float(item.get("rr") or 0)
    radar = float(item.get("radar_score") or 0)
    entry = float(item.get("entry_score") or 0)
    rank = float(item.get("rank_score") or 0)
    cat_score = float(catalyst.get("score") or 50)

    group_state = (
        ctx.get("groups", {})
        .get(item.get("group"), {})
        .get("state", "unknown")
    )
    market_state = ctx.get("market", "unknown")

    # Core quality: 0-70 points
    score = (
        radar * 0.20
        + entry * 0.22
        + rank * 0.12
        + min(max(rr, 0), 3) / 3 * 8
        + cat_score * 0.12
    )

    # Context/freshness: deliberately small so one factor cannot dominate.
    score += min(4, max(-4, _freshness_bonus(item.get("confidence_code")) * 0.55))
    score += min(4, max(-4, _context_bonus(market_state) * 0.65))
    score += min(5, max(-5, _context_bonus(group_state) * 0.75))

    # Catalyst direction adds a modest final adjustment.
    sentiment = catalyst.get("sentiment", "unknown")
    score += {"positive": 4, "negative": -6, "neutral": 0, "unknown": -1}.get(sentiment, 0)
    if catalyst.get("negative_high_impact"):
        score -= 10

    action = item.get("action_code", "WAIT")
    score += {
        "ENTER": 4,
        "SCALE": 2,
        "WAIT": -5,
        "DONT_CHASE": -12,
        "AVOID": -22,
    }.get(action, -7)

    # Calibration band: exceptional setups can reach the high 80s/low 90s,
    # but routine candidates should not cluster at 100.
    return round(max(0, min(94, score)), 1)


def _top_pick_label(item, position):
    score = item["watch_score"]
    action = item.get("action_code")
    confidence = item.get("confidence_code")

    if confidence == "CACHED" or action == "AVOID":
        return "SKIP", "🚫 Skip"

    if position == 0 and score >= 72 and action in ("ENTER", "SCALE"):
        return "TOP", "🏆 Top Pick"

    if position <= 2 and score >= 64 and action in ("ENTER", "SCALE", "WAIT"):
        return "BACKUP", "🥈 Backup Pick"

    if action == "DONT_CHASE":
        return "WAIT", "🟠 รอ Pullback"

    if score >= 50:
        return "WAIT", "⏳ Wait"

    return "SKIP", "🚫 Skip"


def build_top_picks(force=False):
    now = time.time()

    if (
        not force
        and _TOP_PICK_CACHE["data"] is not None
        and now - _TOP_PICK_CACHE["ts"] < _TOP_PICK_TTL
    ):
        cached = dict(_TOP_PICK_CACHE["data"])
        cached["from_cache"] = True
        return cached

    scan = scan_watchlist(force=force)
    ctx = scan.get("auto_context") or {"market": "unknown", "groups": {}}

    # Start from the technically best candidates only.
    eligible = [
        x for x in scan.get("results", [])
        if x.get("confidence_code") != "CACHED"
        and x.get("action_code") in ("ENTER", "SCALE", "WAIT", "DONT_CHASE")
    ]

    # Keep news workload small on Render Free.
    eligible.sort(
        key=lambda x: (
            0 if x.get("action_code") in ("ENTER", "SCALE") else 1,
            -float(x.get("rank_score") or 0),
            -float(x.get("entry_score") or 0),
        )
    )

    news_targets = eligible[:_TOP_PICK_NEWS_LIMIT]
    catalyst_map = {}

    for item in news_targets:
        ticker = item["ticker"]
        try:
            catalyst_map[ticker] = _get_catalyst(ticker, False)
        except Exception:
            catalyst_map[ticker] = {
                "ticker": ticker,
                "score": 50,
                "sentiment": "unknown",
                "label": "⚪ ข่าวยังไม่พร้อม",
                "reason": "โหลด Catalyst ไม่สำเร็จ",
                "items": [],
                "negative_high_impact": False,
            }
        # small pause is friendlier to free data source
        time.sleep(0.15)

    ranked = []
    for item in eligible:
        cat = catalyst_map.get(item["ticker"], {
            "ticker": item["ticker"],
            "score": 50,
            "sentiment": "unknown",
            "label": "⚪ ยังไม่ได้โหลด Catalyst",
            "reason": "V4.2 โหลดข่าวอัตโนมัติเฉพาะตัวอันดับต้นเพื่อประหยัดทรัพยากร",
            "items": [],
            "negative_high_impact": False,
        })

        x = dict(item)
        x["catalyst"] = {
            "score": cat.get("score", 50),
            "sentiment": cat.get("sentiment", "unknown"),
            "label": cat.get("label", "⚪ ยังไม่ได้โหลด Catalyst"),
            "reason": cat.get("reason", ""),
            "negative_high_impact": bool(cat.get("negative_high_impact")),
        }

        group_state = (
            ctx.get("groups", {})
            .get(x.get("group"), {})
            .get("state", "unknown")
        )
        x["market_state"] = ctx.get("market", "unknown")
        x["group_state"] = group_state
        x["watch_score"] = _top_pick_score(x, ctx, cat)
        ranked.append(x)

    ranked.sort(
        key=lambda x: (
            bool(x["catalyst"].get("negative_high_impact")),
            -float(x.get("watch_score") or 0),
            -float(x.get("entry_score") or 0),
            -float(x.get("rr") or 0),
        )
    )

    # Attach display labels after sorting
    for i, x in enumerate(ranked):
        code, label = _top_pick_label(x, i)
        x["pick_code"] = code
        x["pick_label"] = label
        x["pick_rank"] = i + 1

        reasons = []
        if x.get("confidence_code") == "FRESH":
            reasons.append("ข้อมูลเทคนิค Fresh")
        elif x.get("confidence_code") == "RECOVERED":
            reasons.append("ข้อมูลกู้กลับสำเร็จ")

        if x.get("market_state") == "bull":
            reasons.append("ภาพรวม Watchlist แข็งแรง")
        elif x.get("market_state") == "bear":
            reasons.append("ภาพรวม Watchlist อ่อน")

        if x.get("group_state") == "bull":
            reasons.append("กลุ่มหุ้นแข็งแรง")
        elif x.get("group_state") == "bear":
            reasons.append("กลุ่มหุ้นอ่อน")

        if x["catalyst"].get("sentiment") == "positive":
            reasons.append("Catalyst เชิงบวก")
        elif x["catalyst"].get("sentiment") == "negative":
            reasons.append("Catalyst เชิงลบ")
        else:
            reasons.append("Catalyst ยังไม่ชัด")

        if float(x.get("rr") or 0) >= 2:
            reasons.append("R/R ถึง TP1 ≥ 2")

        x["pick_reasons"] = reasons[:4]


    # V4.2: distance from #1 + concise reason why leader is ahead.
    if ranked:
        leader = ranked[0]
        leader_score = float(leader.get("watch_score") or 0)
        for item in ranked:
            item["gap_from_top"] = round(
                leader_score - float(item.get("watch_score") or 0), 1
            )

        if len(ranked) > 1:
            second = ranked[1]
            diffs = []
            cat_gap = float(leader["catalyst"].get("score") or 50) - float(second["catalyst"].get("score") or 50)
            rr_gap = float(leader.get("rr") or 0) - float(second.get("rr") or 0)
            entry_gap = float(leader.get("entry_score") or 0) - float(second.get("entry_score") or 0)
            radar_gap = float(leader.get("radar_score") or 0) - float(second.get("radar_score") or 0)

            if abs(cat_gap) >= 3:
                diffs.append(f"Catalyst {'+' if cat_gap > 0 else ''}{cat_gap:.0f}")
            if abs(rr_gap) >= 0.15:
                diffs.append(f"R/R {'+' if rr_gap > 0 else ''}{rr_gap:.2f}")
            if abs(entry_gap) >= 3:
                diffs.append(f"Entry {'+' if entry_gap > 0 else ''}{entry_gap:.0f}")
            if abs(radar_gap) >= 3:
                diffs.append(f"Radar {'+' if radar_gap > 0 else ''}{radar_gap:.0f}")

            leader["why_leads"] = (
                f"{leader['ticker']} นำ {second['ticker']} เพราะ " + ", ".join(diffs[:3])
                if diffs
                else f"{leader['ticker']} นำ {second['ticker']} จากคะแนนรวมที่ดีกว่าเล็กน้อย"
            )
        else:
            leader["why_leads"] = "มี Candidate ที่ผ่านเกณฑ์เพียงตัวเดียว"

    top = ranked[:8]

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "market": ctx.get("market", "unknown"),
        "scan_total": scan.get("total", 0),
        "scan_requested": scan.get("requested", 0),
        "missing": scan.get("failed", 0),
        "top_picks": top,
        "from_cache": False,
        "note": (
            "V4.2 Watch Score ใช้เพื่อจัดลำดับหุ้นที่ควรเฝ้าก่อน "
            "ไม่ใช่เปอร์เซ็นต์โอกาสชนะ และยังต้องใส่ราคาสด Webull เพื่อ Final Decision"
        ),
    }

    _TOP_PICK_CACHE["ts"] = now
    _TOP_PICK_CACHE["data"] = payload
    return payload


def _clamp(x):return max(0,min(100,x))

def _auto_confirm(p):
    price=float(p["price"]); lo=float(p["buy_low"]); hi=float(p["buy_high"])
    stop=float(p["stop"]); tp1=float(p["tp1"])
    confidence=p.get("data_confidence","FRESH")
    market=p.get("market","unknown"); sector=p.get("sector","unknown")
    catalyst=p.get("catalyst","unknown"); catalyst_score=float(p.get("catalyst_score") or 50)
    negative_high_impact=bool(p.get("negative_high_impact"))

    # V4.2 Premarket Gate inputs are entered from Webull.
    premarket_pct_raw=p.get("premarket_pct")
    rel_volume_raw=p.get("rel_volume")

    def optional_float(v):
        try:
            if v is None or v=="":
                return None
            return float(v)
        except Exception:
            return None

    premarket_pct=optional_float(premarket_pct_raw)
    rel_volume=optional_float(rel_volume_raw)

    def done(status,score,label,reason,checks,missing=None,gate=None):
        return {
            "status":status,
            "score":round(_clamp(score)),
            "label":label,
            "reason":reason,
            "checks":checks,
            "missing":missing or [],
            "premarket_gate":gate or {
                "status":"UNKNOWN",
                "label":"⚪ Premarket Gate ยังไม่ครบ",
                "score_adjustment":0,
            },
        }

    if confidence=="CACHED":
        return done("BLOCK",0,"🔴 งดเข้า","ข้อมูลหุ้นเป็น Cache — ต้องรีเฟรชก่อนตัดสินใจ",
                    ["🔴 ข้อมูลหุ้นไม่ Fresh"],["รีเฟรชข้อมูลให้เป็น Fresh/Recovered"])
    if price<stop:
        return done("BLOCK",0,"🔴 งดเข้า","ราคาหลุด Stop / จุดที่แผนผิด",
                    ["🔴 ราคาต่ำกว่า Stop"],["รอสร้างโครงสร้างราคาใหม่"])
    if price>=tp1:
        return done("DONT_CHASE",10,"🟠 ไม่ไล่ราคา","ราคาถึงหรือเกิน TP1 แล้ว",
                    ["🔴 Risk/Reward ไม่เหมาะกับการเข้าใหม่"],["รอ Pullback และประเมิน Buy Zone ใหม่"])

    score=50; checks=[]; missing=[]

    if lo<=price<=hi:
        score+=22; checks.append("🟢 ราคาอยู่ใน Buy Zone")
    elif price<lo:
        score-=8; checks.append("🟡 ราคาต่ำกว่า Buy Zone")
        missing.append("รอราคากลับเข้า Buy Zone พร้อมแรงซื้อยืนยัน")
    else:
        score-=10; checks.append("🟠 ราคาเหนือ Buy Zone")
        missing.append("รอราคาย่อลงกลับเข้า Buy Zone — ไม่ไล่ราคา")

    if market=="bull":
        score+=10; checks.append("🟢 ภาพรวม Watchlist แข็งแรง")
    elif market=="bear":
        score-=14; checks.append("🔴 ภาพรวม Watchlist อ่อน")
        missing.append("รอภาพรวม Watchlist ฟื้น")
    elif market=="neutral":
        checks.append("⚪ ภาพรวม Watchlist กลาง")
        missing.append("ภาพรวม Watchlist แข็งแรงขึ้นจะเพิ่มความมั่นใจ")
    else:
        checks.append("⚪ Market context ยังไม่พอ")
        missing.append("รอ Market context ให้พร้อม")

    if sector=="bull":
        score+=10; checks.append("🟢 กลุ่มหุ้นเดียวกันแข็งแรง")
    elif sector=="bear":
        score-=14; checks.append("🔴 กลุ่มหุ้นเดียวกันอ่อน")
        missing.append("รอกลุ่มหุ้นฟื้น")
    elif sector=="neutral":
        checks.append("⚪ กลุ่มหุ้นกลาง")
        missing.append("กลุ่มหุ้นแข็งแรงขึ้นจะเพิ่มความมั่นใจ")
    else:
        checks.append("⚪ ข้อมูลกลุ่มยังไม่พอ")
        missing.append("รอข้อมูลกลุ่มหุ้นให้พร้อม")

    if catalyst=="positive":
        score+=min(10,max(3,round((catalyst_score-50)/3)))
        checks.append(f"🟢 Catalyst เป็นบวก ({round(catalyst_score)}/100)")
    elif catalyst=="negative":
        score-=min(20,max(8,round((50-catalyst_score)/2)))
        checks.append(f"🔴 Catalyst เป็นลบ ({round(catalyst_score)}/100)")
        missing.append("รอ Catalyst ลบคลี่คลายหรือมีข่าวใหม่ยืนยัน")
    elif catalyst=="neutral":
        checks.append("⚪ Catalyst ยังกลาง")
        missing.append("Catalyst บวกจะช่วยเพิ่มความมั่นใจ")
    else:
        checks.append("⚪ ข่าวยังไม่พร้อม")
        missing.append("รอ Catalyst/ข่าวให้พร้อม")

    # ---------------- Premarket Gate ----------------
    gate_adjust=0
    gate_checks=[]
    gate_missing=[]
    hard_block=False
    no_chase=False

    if premarket_pct is None:
        gate_checks.append("⚪ ยังไม่ได้ใส่ % Premarket")
        gate_missing.append("ใส่ % Premarket จาก Webull เพื่อยืนยันแรงก่อนเปิด")
    else:
        if -2.0 <= premarket_pct <= 3.0:
            gate_adjust += 5
            gate_checks.append(f"🟢 Premarket {premarket_pct:+.2f}% อยู่ในช่วงไม่ร้อนเกิน")
        elif 3.0 < premarket_pct <= 6.0:
            gate_adjust -= 2
            gate_checks.append(f"🟡 Premarket {premarket_pct:+.2f}% เริ่มแรง — ระวังไล่ราคา")
            gate_missing.append("รอให้ราคายืนยันว่าไม่เปิด Gap สูงเกิน Buy Zone")
        elif premarket_pct > 6.0:
            gate_adjust -= 12
            no_chase=True
            gate_checks.append(f"🟠 Premarket {premarket_pct:+.2f}% ร้อนเกินสำหรับการไล่ราคา")
            gate_missing.append("รอ Pullback / ฐานราคาใหม่หลังเปิด")
        elif -5.0 <= premarket_pct < -2.0:
            gate_adjust -= 7
            gate_checks.append(f"🟡 Premarket {premarket_pct:+.2f}% อ่อน")
            gate_missing.append("รอแรงซื้อกลับก่อนเข้า")
        else:
            gate_adjust -= 18
            hard_block=True
            gate_checks.append(f"🔴 Premarket {premarket_pct:+.2f}% ผิดปกติ/อ่อนมาก")
            gate_missing.append("งดเข้าใหม่จนกว่าจะเห็นการฟื้นตัวชัด")

    if rel_volume is None:
        gate_checks.append("⚪ ยังไม่ได้ใส่ Relative Volume")
        gate_missing.append("ใส่ Relative Volume จาก Webull ถ้ามี")
    else:
        if 1.2 <= rel_volume <= 3.0:
            gate_adjust += 7
            gate_checks.append(f"🟢 Relative Volume {rel_volume:.2f}x สนับสนุนการเคลื่อนไหว")
        elif 0.8 <= rel_volume < 1.2:
            gate_adjust += 1
            gate_checks.append(f"⚪ Relative Volume {rel_volume:.2f}x ปกติ")
        elif rel_volume < 0.8:
            gate_adjust -= 5
            gate_checks.append(f"🟡 Relative Volume {rel_volume:.2f}x เบา")
            gate_missing.append("รอ Volume ยืนยัน")
        else:
            gate_adjust += 2
            gate_checks.append(f"🟡 Relative Volume {rel_volume:.2f}x สูงมาก — มี Momentum แต่ผันผวน")
            gate_missing.append("อย่าไล่ราคา ใช้ Buy Zone เป็นหลัก")

    score += gate_adjust
    checks.extend(gate_checks)
    missing.extend(gate_missing)

    if hard_block:
        gate_status="BLOCK"
        gate_label="🔴 Premarket Gate ไม่ผ่าน"
    elif no_chase:
        gate_status="HOT"
        gate_label="🟠 Premarket Gate: ร้อนเกิน"
    elif premarket_pct is not None and rel_volume is not None and gate_adjust>=8:
        gate_status="PASS"
        gate_label="🟢 Premarket Gate ผ่าน"
    elif premarket_pct is not None or rel_volume is not None:
        gate_status="CAUTION"
        gate_label="🟡 Premarket Gate ผ่านแบบระวัง"
    else:
        gate_status="UNKNOWN"
        gate_label="⚪ Premarket Gate ยังไม่ครบ"

    gate={
        "status":gate_status,
        "label":gate_label,
        "score_adjustment":gate_adjust,
        "premarket_pct":premarket_pct,
        "rel_volume":rel_volume,
    }

    score=round(_clamp(score))

    if negative_high_impact:
        return done("BLOCK",score,"🔴 งดเข้า","พบข่าวลบ Impact สูง — รอให้ตลาดย่อยข่าวก่อน",
                    checks,["รอผลกระทบจากข่าวลบ Impact สูงคลี่คลาย"],gate)
    if hard_block:
        return done("BLOCK",score,"🔴 งดเข้า","Premarket อ่อน/ผิดปกติจน Gate ไม่ผ่าน",
                    checks,missing,gate)
    if market=="bear" and sector=="bear":
        return done("BLOCK",score,"🔴 งดเข้า","ภาพรวม Watchlist และกลุ่มหุ้นอ่อนพร้อมกัน",
                    checks,missing,gate)
    if no_chase or price>hi:
        return done("DONT_CHASE",score,"🟠 ไม่ไล่ราคา",
                    "ราคา/แรง Premarket ร้อนเกิน Buy Zone สำหรับการเข้าใหม่",
                    checks,missing,gate)
    if price<lo:
        return done("WAIT",score,"🟡 รอ Pullback / Trigger",
                    "ราคายังต่ำกว่า Buy Zone — รอการยืนยันก่อนเข้าไม้ 1",
                    checks,missing,gate)

    # For a green light in V4.2, Premarket Gate must be at least partially supplied.
    gate_has_data = premarket_pct is not None or rel_volume is not None
    if score>=82 and gate_has_data and gate_status in ("PASS","CAUTION"):
        return done("CONFIRMED",score,"🟢 เข้าไม้ 1",
                    "ราคาอยู่ใน Buy Zone และ Premarket Gate + Context ผ่านเกณฑ์",
                    checks,[],gate)

    if not gate_has_data:
        return done("WAIT",score,"🟡 รอ Premarket Gate",
                    "Technical/Context อาจดี แต่ยังไม่ได้ยืนยันข้อมูล Premarket จาก Webull",
                    checks,missing,gate)

    if score>=64:
        return done("WAIT",score,"🟡 เฝ้ารอ Trigger",
                    "ราคาอยู่ใน Buy Zone แต่เงื่อนไขรวมยังไม่แข็งแรงพอสำหรับไฟเขียว",
                    checks,missing,gate)

    return done("WAIT",score,"🟡 เฝ้ารอ Trigger",
                "Decision Engine ยังไม่ผ่านเกณฑ์เข้าไม้ 1",
                checks,missing,gate)

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



@app.route("/api/top-picks")
def top_picks():
    try:
        force = request.args.get("force") == "1"
        return jsonify({"ok": True, "data": build_top_picks(force)}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/catalyst/<ticker>")
def catalyst(ticker):
    try:
        return jsonify({"ok":True,"data":_get_catalyst(ticker.upper(), request.args.get("force")=="1")}),200
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),200

@app.route("/api/auto-confirm",methods=["POST"])
def auto_confirm():
    try:return jsonify({"ok":True,"data":_auto_confirm(request.get_json(silent=True) or {})}),200
    except Exception as e:return jsonify({"ok":False,"error":str(e)}),200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=False)
