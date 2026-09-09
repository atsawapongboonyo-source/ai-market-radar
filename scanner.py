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

POSITIVE_WORDS = (
    "beat","beats","raises","upgrade","record","growth","surge","strong",
    "contract","deal","partnership","wins","launch","expands","demand",
    "order","outperform"
)

NEGATIVE_WORDS = (
    "miss","misses","cuts","downgrade","probe","lawsuit","warning","weak",
    "decline","falls","delay","recall","investigation","underperform"
)

HIGH_IMPACT_WORDS = (
    "earnings","guidance","revenue","profit","contract","deal","partnership",
    "upgrade","downgrade","investigation","lawsuit","order","forecast","outlook"
)

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
                x = json.load(f)
            return x if isinstance(x, dict) else {}
    except Exception:
        pass
    return {}


def _save_ticker_cache(cache):
    try:
        with _TICKER_CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _build(ticker):
    d = analyze_history(ticker)

    rr = d.get("risk_reward_tp1") or 0
    action = d.get("action_code", "WAIT")
    radar = d.get("score") or 0
    entry = d.get("entry_score") or 0

    bonus = {
        "ENTER": 16,
        "SCALE": 12,
        "WAIT": 5,
        "DONT_CHASE": -2,
        "AVOID": -12
    }.get(action, 0)

    rr_bonus = min(max(rr, 0), 3) / 3 * 8

    rank = round(
        max(
            0,
            min(
                100,
                radar * .42
                + entry * .48
                + rr_bonus
                + bonus
            )
        ),
        1
    )

    labels = {
        "ENTER": ("🟦 Candidate — รอราคาสด", "candidate"),
        "SCALE": ("🟦 Candidate — รอราคาสด", "candidate"),
        "WAIT": ("🟡 รอจังหวะ", "wait"),
        "DONT_CHASE": ("🟠 ไม่ไล่ราคา", "chase"),
        "AVOID": ("🔴 ยังไม่เข้า", "avoid")
    }

    label, cls = labels.get(action, labels["WAIT"])

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
        "scanner_label": label,
        "scanner_class": cls,
        "rank_score": rank,
        "data_date": d.get("data_date"),
        "group": _group_for(ticker),
        "confidence_code": "FRESH",
        "confidence_score": 100,
        "freshness_label": "🟢 Fresh"
    }


def _try(ticker, retries=2):
    err = None

    for i in range(retries + 1):
        try:
            return _build(ticker), None, i
        except Exception as e:
            err = str(e)

            if i < retries:
                time.sleep(.75 * (i + 1))

    return None, {
        "ticker": ticker,
        "error": err or "unknown"
    }, retries


def _cached(ticker, cache, now):
    item = cache.get(ticker)

    if not isinstance(item, dict):
        return None

    saved = item.get("_saved_at")
    data = item.get("data")

    if not saved or not isinstance(data, dict):
        return None

    age = now - float(saved)

    if age < 0 or age > _TICKER_CACHE_MAX_AGE:
        return None

    r = dict(data)

    r["confidence_code"] = "CACHED"
    r["confidence_score"] = (
        70 if age <= 86400
        else 55 if age <= 172800
        else 40
    )

    r["freshness_label"] = "⚪ Cached"
    r["scanner_label"] = "⚪ Cache — ต้องยืนยันข้อมูลใหม่"
    r["scanner_class"] = "cached"

    return r


def _derive_context(results):
    """
    ใช้ breadth ของ watchlist เป็น market/sector proxy
    โดยไม่อ้างว่าเป็นราคาสด QQQ
    """

    usable = [
        x for x in results
        if x.get("confidence_code") != "CACHED"
    ]

    if not usable:
        return {
            "market": "unknown",
            "market_score": 0,
            "groups": {}
        }

    def strength(items):
        if not items:
            return 0

        vals = []

        for x in items:
            a = x.get("action_code")

            vals.append({
                "ENTER": 1,
                "SCALE": .8,
                "WAIT": 0,
                "DONT_CHASE": -.35,
                "AVOID": -1
            }.get(a, 0))

        return sum(vals) / len(vals)

    all_s = strength(usable)

    market = (
        "bull" if all_s >= .22
        else "bear" if all_s <= -.22
        else "neutral"
    )

    gs = {}

    for g in GROUPS:
        members = [
            x for x in usable
            if x.get("group") == g
        ]

        s = strength(members)

        gs[g] = {
            "state": (
                "bull" if s >= .25
                else "bear" if s <= -.25
                else "neutral"
            ),
            "strength": round(s, 2),
            "count": len(members)
        }

    return {
        "market": market,
        "market_score": round(all_s, 2),
        "groups": gs
    }


def scan_watchlist(force=False):
    now = time.time()

    if (
        not force
        and _SCAN_CACHE["data"]
        and now - _SCAN_CACHE["ts"] < _SCAN_TTL
    ):
        x = dict(_SCAN_CACHE["data"])
        x["from_cache"] = True
        return x

    tickers = [
        x["ticker"]
        for x in load_json("watchlist.json")
    ]

    cache = _load_ticker_cache()

    fresh = []
    recovered = []
    cached = []
    errors = []
    failed = []

    with ThreadPoolExecutor(max_workers=2) as ex:
        fs = {
            ex.submit(_try, t): t
            for t in tickers
        }

        for f in as_completed(fs):
            t = fs[f]

            r, e, n = f.result()

            if r:
                fresh.append(r)
                cache[t] = {
                    "_saved_at": now,
                    "data": r
                }
            else:
                failed.append((t, e))

    # Recovery Queue แบบทีละตัว
    for t, e in failed:
        time.sleep(1.2)

        r, e2, n = _try(t, 1)

        if r:
            r["confidence_code"] = "RECOVERED"
            r["confidence_score"] = 85
            r["freshness_label"] = "🟡 Recovered"

            recovered.append(r)

            cache[t] = {
                "_saved_at": now,
                "data": r
            }

        else:
            c = _cached(t, cache, now)

            if c:
                cached.append(c)
            else:
                errors.append(e2 or e)

    _save_ticker_cache(cache)

    results = fresh + recovered + cached

    ctx = _derive_context(results)

    order = {
        "ENTER": 0,
        "SCALE": 1,
        "WAIT": 2,
        "DONT_CHASE": 3,
        "AVOID": 4
    }

    conf = {
        "FRESH": 0,
        "RECOVERED": 1,
        "CACHED": 2
    }

    results.sort(
        key=lambda x: (
            conf.get(x["confidence_code"], 9),
            order.get(x["action_code"], 9),
            -x["rank_score"]
        )
    )

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "requested": len(tickers),
        "total": len(results),
        "failed": len(errors),
        "fresh_count": len(fresh),
        "recovered_count": len(recovered),
        "fallback_used": len(cached),
        "errors": errors,
        "results": results,
        "auto_context": ctx,
        "from_cache": False,
        "note": (
            "V4.5.2 Scanner + Auto Context + Catalyst + "
            "Premarket Gate + Final Decision"
        )
    }

    _SCAN_CACHE.update({
        "ts": now,
        "data": payload
    })

    return payload


def _news_fields(item):
    if not isinstance(item, dict):
        return None

    c = (
        item.get("content")
        if isinstance(item.get("content"), dict)
        else item
    )

    title = (
        c.get("title")
        or c.get("headline")
        or item.get("title")
        or ""
    )

    provider = c.get("provider")

    publisher = (
        provider.get("displayName")
        or provider.get("name")
        or ""
    ) if isinstance(provider, dict) else (
        c.get("publisher")
        or item.get("publisher")
        or ""
    )

    link = ""

    for key in ("canonicalUrl", "clickThroughUrl"):
        v = c.get(key)

        if isinstance(v, dict) and v.get("url"):
            link = v["url"]
            break

    link = (
        link
        or item.get("link")
        or c.get("link")
        or ""
    )

    published = (
        c.get("pubDate")
        or c.get("displayTime")
        or item.get("providerPublishTime")
    )

    return {
        "title": str(title).strip(),
        "publisher": str(publisher).strip(),
        "link": str(link).strip(),
        "published": published
    }


def _age_hours(v):
    try:
        if v is None:
            return None

        if isinstance(v, (int, float)):
            dt = datetime.fromtimestamp(
                v,
                tz=timezone.utc
            )
        else:
            dt = datetime.fromisoformat(
                str(v).replace(
                    "Z",
                    "+00:00"
                )
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

        return max(
            0,
            (
                datetime.now(timezone.utc)
                - dt.astimezone(timezone.utc)
            ).total_seconds() / 3600
        )

    except Exception:
        return None


def _classify_title(title):
    t = title.lower()

    pos = sum(
        1 for w in POSITIVE_WORDS
        if w in t
    )

    neg = sum(
        1 for w in NEGATIVE_WORDS
        if w in t
    )

    high = any(
        w in t
        for w in HIGH_IMPACT_WORDS
    )

    if neg > pos:
        return "negative", -1, high

    if pos > neg:
        return "positive", 1, high

    return "neutral", 0, high


def _get_catalyst(ticker, force=False):
    now = time.time()

    hit = _CATALYST_CACHE.get(ticker)

    if (
        hit
        and not force
        and now - hit["ts"] < _CATALYST_TTL
    ):
        d = dict(hit["data"])
        d["from_cache"] = True
        return d

    try:
        raw = yf.Ticker(ticker).news or []

    except Exception as e:
        return {
            "ticker": ticker,
            "score": 50,
            "sentiment": "unknown",
            "label": "⚪ ข่าวยังไม่พร้อม",
            "reason": "แหล่งข่าวฟรีไม่ตอบกลับ",
            "items": [],
            "negative_high_impact": False,
            "error": str(e)
        }

    items = []
    weighted = 0
    total = 0
    neg_high = False

    for raw_item in raw[:12]:
        x = _news_fields(raw_item)

        if not x or not x["title"]:
            continue

        sent, base, high = _classify_title(
            x["title"]
        )

        age = _age_hours(
            x["published"]
        )

        rw = (
            1.0 if age is not None and age <= 24
            else .7 if age is not None and age <= 72
            else .4 if age is not None and age <= 168
            else .2
        )

        w = rw * (
            1.35 if high
            else 1
        )

        weighted += base * w
        total += w

        if (
            sent == "negative"
            and high
            and (
                age is None
                or age <= 72
            )
        ):
            neg_high = True

        x.update({
            "sentiment": sent,
            "high_impact": high,
            "age_hours": (
                round(age, 1)
                if age is not None
                else None
            )
        })

        items.append(x)

        if len(items) >= 6:
            break

    if not items:
        data = {
            "ticker": ticker,
            "score": 50,
            "sentiment": "neutral",
            "label": "⚪ ยังไม่พบ Catalyst ชัด",
            "reason": "ไม่พบหัวข้อข่าวจากแหล่งฟรี",
            "items": [],
            "negative_high_impact": False
        }

    else:
        ratio = (
            weighted / total
            if total
            else 0
        )

        score = round(
            max(
                0,
                min(
                    100,
                    50 + ratio * 28
                )
            )
        )

        if neg_high:
            sent = "negative"
            label = "🔴 มี Risk Catalyst"
            reason = (
                "พบข่าวลบ Impact สูง"
                "ในช่วงล่าสุด"
            )

        elif score >= 63:
            sent = "positive"
            label = "🟢 Positive Catalyst"
            reason = (
                "หัวข้อข่าวล่าสุด"
                "มีน้ำหนักเชิงบวก"
            )

        elif score <= 37:
            sent = "negative"
            label = "🔴 Negative Catalyst"
            reason = (
                "หัวข้อข่าวล่าสุด"
                "มีน้ำหนักเชิงลบ"
            )

        else:
            sent = "neutral"
            label = "⚪ Catalyst กลาง"
            reason = (
                "ข่าวล่าสุดยังไม่ให้ทิศทางชัด"
            )

        data = {
            "ticker": ticker,
            "score": score,
            "sentiment": sent,
            "label": label,
            "reason": reason,
            "items": items,
            "negative_high_impact": neg_high
        }

    _CATALYST_CACHE[ticker] = {
        "ts": now,
        "data": data
    }

    return data


def _freshness_bonus(code):
    return {
        "FRESH": 8,
        "RECOVERED": 3,
        "CACHED": -18
    }.get(code, -10)


def _context_bonus(state):
    return {
        "bull": 8,
        "neutral": 0,
        "bear": -10,
        "unknown": -4
    }.get(state, -4)


def _catalyst_bonus(cat):
    sent = cat.get(
        "sentiment",
        "unknown"
    )

    score = float(
        cat.get("score")
        or 50
    )

    if cat.get(
        "negative_high_impact"
    ):
        return -28

    if sent == "positive":
        return min(
            12,
            max(
                4,
                (score - 50) * 0.35
            )
        )

    if sent == "negative":
        return -min(
            20,
            max(
                8,
                (50 - score) * 0.45
            )
        )

    if sent == "neutral":
        return 0

    return -3


def _top_pick_score(
    item,
    ctx,
    catalyst
):
    """
    Watch Score ใช้เพื่อจัดลำดับหุ้น
    ไม่ใช่ win probability
    และไม่ใช่คำสั่งซื้อ
    """

    rr = float(
        item.get("rr")
        or 0
    )

    radar = float(
        item.get("radar_score")
        or 0
    )

    entry = float(
        item.get("entry_score")
        or 0
    )

    rank = float(
        item.get("rank_score")
        or 0
    )

    cat_score = float(
        catalyst.get("score")
        or 50
    )

    group_state = (
        ctx.get("groups", {})
        .get(
            item.get("group"),
            {}
        )
        .get(
            "state",
            "unknown"
        )
    )

    market_state = ctx.get(
        "market",
        "unknown"
    )

    score = (
        radar * 0.20
        + entry * 0.22
        + rank * 0.12
        + min(
            max(rr, 0),
            3
        ) / 3 * 8
        + cat_score * 0.12
    )

    score += min(
        4,
        max(
            -4,
            _freshness_bonus(
                item.get(
                    "confidence_code"
                )
            ) * 0.55
        )
    )

    score += min(
        4,
        max(
            -4,
            _context_bonus(
                market_state
            ) * 0.65
        )
    )

    score += min(
        5,
        max(
            -5,
            _context_bonus(
                group_state
            ) * 0.75
        )
    )

    sentiment = catalyst.get(
        "sentiment",
        "unknown"
    )

    score += {
        "positive": 4,
        "negative": -6,
        "neutral": 0,
        "unknown": -1
    }.get(
        sentiment,
        0
    )

    if catalyst.get(
        "negative_high_impact"
    ):
        score -= 10

    action = item.get(
        "action_code",
        "WAIT"
    )

    score += {
        "ENTER": 4,
        "SCALE": 2,
        "WAIT": -5,
        "DONT_CHASE": -12,
        "AVOID": -22
    }.get(
        action,
        -7
    )

    return round(
        max(
            0,
            min(
                94,
                score
            )
        ),
        1
    )


def _top_pick_label(
    item,
    position
):
    score = item["watch_score"]

    action = item.get(
        "action_code"
    )

    confidence = item.get(
        "confidence_code"
    )

    if (
        confidence == "CACHED"
        or action == "AVOID"
    ):
        return (
            "SKIP",
            "🚫 Skip"
        )

    if (
        position == 0
        and score >= 72
        and action in (
            "ENTER",
            "SCALE"
        )
    ):
        return (
            "TOP",
            "🏆 Top Pick"
        )

    if (
        position <= 2
        and score >= 64
        and action in (
            "ENTER",
            "SCALE",
            "WAIT"
        )
    ):
        return (
            "BACKUP",
            "🥈 Backup Pick"
        )

    if action == "DONT_CHASE":
        return (
            "WAIT",
            "🟠 รอ Pullback"
        )

    if score >= 50:
        return (
            "WAIT",
            "⏳ Wait"
        )

    return (
        "SKIP",
        "🚫 Skip"
    )


def build_top_picks(force=False):
    now = time.time()

    if (
        not force
        and _TOP_PICK_CACHE["data"] is not None
        and now - _TOP_PICK_CACHE["ts"] < _TOP_PICK_TTL
    ):
        cached = dict(
            _TOP_PICK_CACHE["data"]
        )

        cached["from_cache"] = True

        return cached

    scan = scan_watchlist(
        force=force
    )

    ctx = (
        scan.get("auto_context")
        or {
            "market": "unknown",
            "groups": {}
        }
    )

    eligible = [
        x for x in scan.get(
            "results",
            []
        )
        if x.get(
            "confidence_code"
        ) != "CACHED"
        and x.get(
            "action_code"
        ) in (
            "ENTER",
            "SCALE",
            "WAIT",
            "DONT_CHASE"
        )
    ]

    eligible.sort(
        key=lambda x: (
            0 if x.get(
                "action_code"
            ) in (
                "ENTER",
                "SCALE"
            )
            else 1,
            -float(
                x.get(
                    "rank_score"
                )
                or 0
            ),
            -float(
                x.get(
                    "entry_score"
                )
                or 0
            )
        )
    )

    news_targets = eligible[
        :_TOP_PICK_NEWS_LIMIT
    ]

    catalyst_map = {}

    for item in news_targets:
        ticker = item["ticker"]

        try:
            catalyst_map[ticker] = (
                _get_catalyst(
                    ticker,
                    False
                )
            )

        except Exception:
            catalyst_map[ticker] = {
                "ticker": ticker,
                "score": 50,
                "sentiment": "unknown",
                "label": "⚪ ข่าวยังไม่พร้อม",
                "reason": "โหลด Catalyst ไม่สำเร็จ",
                "items": [],
                "negative_high_impact": False
            }

        time.sleep(0.15)

    ranked = []

    for item in eligible:
        cat = catalyst_map.get(
            item["ticker"],
            {
                "ticker": item["ticker"],
                "score": 50,
                "sentiment": "unknown",
                "label": "⚪ ยังไม่ได้โหลด Catalyst",
                "reason": (
                    "โหลดข่าวอัตโนมัติ"
                    "เฉพาะตัวอันดับต้น"
                    "เพื่อประหยัดทรัพยากร"
                ),
                "items": [],
                "negative_high_impact": False
            }
        )

        x = dict(item)

        x["catalyst"] = {
            "score": cat.get(
                "score",
                50
            ),
            "sentiment": cat.get(
                "sentiment",
                "unknown"
            ),
            "label": cat.get(
                "label",
                "⚪ ยังไม่ได้โหลด Catalyst"
            ),
            "reason": cat.get(
                "reason",
                ""
            ),
            "negative_high_impact": bool(
                cat.get(
                    "negative_high_impact"
                )
            )
        }

        group_state = (
            ctx.get("groups", {})
            .get(
                x.get("group"),
                {}
            )
            .get(
                "state",
                "unknown"
            )
        )

        x["market_state"] = ctx.get(
            "market",
            "unknown"
        )

        x["group_state"] = group_state

        x["watch_score"] = (
            _top_pick_score(
                x,
                ctx,
                cat
            )
        )

        ranked.append(x)

    ranked.sort(
        key=lambda x: (
            bool(
                x["catalyst"].get(
                    "negative_high_impact"
                )
            ),
            -float(
                x.get(
                    "watch_score"
                )
                or 0
            ),
            -float(
                x.get(
                    "entry_score"
                )
                or 0
            ),
            -float(
                x.get(
                    "rr"
                )
                or 0
            )
        )
    )

    for i, x in enumerate(ranked):
        code, label = (
            _top_pick_label(
                x,
                i
            )
        )

        x["pick_code"] = code
        x["pick_label"] = label
        x["pick_rank"] = i + 1

        reasons = []

        if (
            x.get(
                "confidence_code"
            ) == "FRESH"
        ):
            reasons.append(
                "ข้อมูลเทคนิค Fresh"
            )

        elif (
            x.get(
                "confidence_code"
            ) == "RECOVERED"
        ):
            reasons.append(
                "ข้อมูลกู้กลับสำเร็จ"
            )

        if (
            x.get(
                "market_state"
            ) == "bull"
        ):
            reasons.append(
                "ภาพรวม Watchlist แข็งแรง"
            )

        elif (
            x.get(
                "market_state"
            ) == "bear"
        ):
            reasons.append(
                "ภาพรวม Watchlist อ่อน"
            )

        if (
            x.get(
                "group_state"
            ) == "bull"
        ):
            reasons.append(
                "กลุ่มหุ้นแข็งแรง"
            )

        elif (
            x.get(
                "group_state"
            ) == "bear"
        ):
            reasons.append(
                "กลุ่มหุ้นอ่อน"
            )

        if (
            x["catalyst"].get(
                "sentiment"
            ) == "positive"
        ):
            reasons.append(
                "Catalyst เชิงบวก"
            )

        elif (
            x["catalyst"].get(
                "sentiment"
            ) == "negative"
        ):
            reasons.append(
                "Catalyst เชิงลบ"
            )

        else:
            reasons.append(
                "Catalyst ยังไม่ชัด"
            )

        if (
            float(
                x.get("rr")
                or 0
            ) >= 2
        ):
            reasons.append(
                "R/R ถึง TP1 ≥ 2"
            )

        x["pick_reasons"] = (
            reasons[:4]
        )

    top = ranked[:8]

    payload = {
        "updated_at": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "market": ctx.get(
            "market",
            "unknown"
        ),
        "scan_total": scan.get(
            "total",
            0
        ),
        "scan_requested": scan.get(
            "requested",
            0
        ),
        "missing": scan.get(
            "failed",
            0
        ),
        "top_picks": top,
        "from_cache": False,
        "note": (
            "V4.5.2 Watch Score "
            "ใช้เพื่อจัดลำดับหุ้นที่ควรเฝ้าก่อน "
            "ไม่ใช่เปอร์เซ็นต์โอกาสชนะ "
            "และยังต้องใส่ราคาสด Webull "
            "เพื่อ Final Decision"
        )
    }

    _TOP_PICK_CACHE["ts"] = now
    _TOP_PICK_CACHE["data"] = payload

    return payload


def _clamp(x):
    return max(
        0,
        min(
            100,
            x
        )
    )


def _auto_confirm(p):
    price = float(
        p["price"]
    )

    lo = float(
        p["buy_low"]
    )

    hi = float(
        p["buy_high"]
    )

    stop = float(
        p["stop"]
    )

    tp1 = float(
        p["tp1"]
    )

    confidence = p.get(
        "data_confidence",
        "FRESH"
    )

    market = p.get(
        "market",
        "unknown"
    )

    sector = p.get(
        "sector",
        "unknown"
    )

    catalyst = p.get(
        "catalyst",
        "unknown"
    )

    catalyst_score = float(
        p.get(
            "catalyst_score"
        )
        or 50
    )

    negative_high_impact = bool(
        p.get(
            "negative_high_impact"
        )
    )

    # V4.5.2 Premarket Gate
    #
    # Current Price:
    #   ต้องมี
    #
    # Premarket:
    #   < -5%      = BLOCK
    #   -5% ถึง < -2% = อ่อน / -6
    #   -2% ถึง < +1% = กลาง
    #   +1% ถึง < +5% = สนับสนุน / +6
    #   >= +5%     = HOT / ไม่ไล่ / -12
    #
    # Relative Volume:
    #   optional
    #   เว้นว่าง = ไม่บวก ไม่ลบ

    pm_raw = p.get(
        "premarket_pct"
    )

    rv_raw = p.get(
        "rel_volume"
    )

    try:
        premarket_pct = (
            None
            if pm_raw in (
                None,
                ""
            )
            else float(pm_raw)
        )

    except (
        TypeError,
        ValueError
    ):
        premarket_pct = None

    try:
        rel_volume = (
            None
            if rv_raw in (
                None,
                ""
            )
            else float(rv_raw)
        )

    except (
        TypeError,
        ValueError
    ):
        rel_volume = None

    gate_status = "PASS"
    gate_label = "🟢 Premarket Gate ผ่าน"
    gate_adjustment = 0
    gate_checks = []
    gate_block = False
    gate_hot = False

    if premarket_pct is None:
        gate_status = "INCOMPLETE"
        gate_label = (
            "⚪ ใส่ % Premarket เพื่อยืนยัน"
        )

        gate_checks.append(
            "⚪ ยังไม่มี % Premarket — "
            "ระบบจะยังไม่ให้ CONFIRMED"
        )

    else:

        if premarket_pct < -5:
            gate_status = "BLOCK"
            gate_label = (
                "🔴 Premarket Gate Block"
            )

            gate_adjustment -= 25
            gate_block = True

            gate_checks.append(
                "🔴 Premarket ต่ำกว่า -5% — "
                "งดเข้าใหม่จนกว่าจะฟื้น"
            )

        elif premarket_pct >= 5:
            gate_status = "HOT"

            gate_label = (
                "🟠 Premarket ร้อน — "
                "ไม่ไล่ราคา"
            )

            gate_adjustment -= 12
            gate_hot = True

            gate_checks.append(
                "🟠 Premarket ตั้งแต่ +5% ขึ้นไป — "
                "Gap-up ร้อน ไม่ไล่ราคา"
            )

        elif 1 <= premarket_pct < 5:
            gate_adjustment += 6

            gate_checks.append(
                "🟢 Premarket เป็นบวก "
                "ในช่วงที่ยอมรับได้ "
                "(+1% ถึงต่ำกว่า +5%)"
            )

        elif -2 <= premarket_pct < 1:
            gate_checks.append(
                "⚪ Premarket กลาง/แกว่งแคบ"
            )

        else:
            gate_adjustment -= 6

            gate_checks.append(
                "🟡 Premarket อ่อน "
                "แต่ยังไม่ถึงระดับ Block"
            )

    if rel_volume is None:
        gate_checks.append(
            "⚪ Relative Volume ไม่ได้กรอก — "
            "ไม่หักคะแนน"
        )

    elif rel_volume < 0:
        rel_volume = None

        gate_checks.append(
            "⚪ Relative Volume ไม่ถูกต้อง — "
            "ไม่นำมาคิดคะแนน"
        )

    elif 1.2 <= rel_volume <= 3.0:
        gate_adjustment += 7

        gate_checks.append(
            "🟢 Relative Volume 1.2x–3.0x "
            "ยืนยัน Momentum"
        )

    elif rel_volume > 3.0:
        gate_adjustment += 2

        gate_checks.append(
            "🟡 Relative Volume สูงมาก — "
            "Momentum แรงแต่เสี่ยงผันผวน"
        )

    elif rel_volume < 0.8:
        gate_adjustment -= 4

        gate_checks.append(
            "🟡 Relative Volume เบา — "
            "แรงยืนยันยังไม่ชัด"
        )

    else:
        gate_checks.append(
            "⚪ Relative Volume อยู่ระดับกลาง"
        )

    gate = {
        "status": gate_status,
        "label": gate_label,
        "score_adjustment": gate_adjustment,
        "premarket_pct": premarket_pct,
        "rel_volume": rel_volume,
        "rel_volume_required": False,
        "checks": gate_checks
    }

    def done(
        status,
        score,
        label,
        reason,
        checks,
        missing=None
    ):
        return {
            "status": status,
            "score": round(
                _clamp(score)
            ),
            "label": label,
            "reason": reason,
            "checks": checks,
            "missing": missing or [],
            "premarket_gate": gate
        }

    if confidence == "CACHED":
        return done(
            "BLOCK",
            0,
            "🔴 งดเข้า",
            (
                "ข้อมูลหุ้นเป็น Cache — "
                "ต้องรีเฟรชก่อนตัดสินใจ"
            ),
            [
                "🔴 ข้อมูลหุ้นไม่ Fresh"
            ] + gate_checks,
            [
                "รีเฟรชข้อมูลให้เป็น Fresh/Recovered"
            ]
        )

    if price < stop:
        return done(
            "BLOCK",
            0,
            "🔴 งดเข้า",
            "ราคาหลุด Stop / จุดที่แผนผิด",
            [
                "🔴 ราคาต่ำกว่า Stop"
            ] + gate_checks,
            [
                "รอสร้างโครงสร้างราคาใหม่"
            ]
        )

    if price >= tp1:
        return done(
            "DONT_CHASE",
            10,
            "🟠 ไม่ไล่ราคา",
            "ราคาถึงหรือเกิน TP1 แล้ว",
            [
                "🔴 Risk/Reward "
                "ไม่เหมาะกับการเข้าใหม่"
            ] + gate_checks,
            [
                "รอ Pullback "
                "และประเมิน Buy Zone ใหม่"
            ]
        )

    score = 50
    checks = []
    missing = []

    if lo <= price <= hi:
        score += 22

        checks.append(
            "🟢 ราคาอยู่ใน Buy Zone"
        )

    elif price < lo:
        score -= 8

        checks.append(
            "🟡 ราคาต่ำกว่า Buy Zone"
        )

        missing.append(
            "รอราคากลับเข้า Buy Zone "
            "พร้อมแรงซื้อยืนยัน"
        )

    else:
        score -= 10

        checks.append(
            "🟠 ราคาเหนือ Buy Zone"
        )

        missing.append(
            "รอราคาย่อลงกลับเข้า Buy Zone — "
            "ไม่ไล่ราคา"
        )

    if market == "bull":
        score += 10

        checks.append(
            "🟢 ภาพรวม Watchlist แข็งแรง"
        )

    elif market == "bear":
        score -= 14

        checks.append(
            "🔴 ภาพรวม Watchlist อ่อน"
        )

        missing.append(
            "รอภาพรวม Watchlist ฟื้น"
        )

    elif market == "neutral":
        checks.append(
            "⚪ ภาพรวม Watchlist กลาง"
        )

        missing.append(
            "ภาพรวม Watchlist แข็งแรงขึ้น "
            "จะเพิ่มความมั่นใจ"
        )

    else:
        checks.append(
            "⚪ Market context ยังไม่พอ"
        )

        missing.append(
            "รอ Market context ให้พร้อม"
        )

    if sector == "bull":
        score += 10

        checks.append(
            "🟢 กลุ่มหุ้นเดียวกันแข็งแรง"
        )

    elif sector == "bear":
        score -= 14

        checks.append(
            "🔴 กลุ่มหุ้นเดียวกันอ่อน"
        )

        missing.append(
            "รอกลุ่มหุ้นฟื้น"
        )

    elif sector == "neutral":
        checks.append(
            "⚪ กลุ่มหุ้นกลาง"
        )

        missing.append(
            "กลุ่มหุ้นแข็งแรงขึ้น "
            "จะเพิ่มความมั่นใจ"
        )

    else:
        checks.append(
            "⚪ ข้อมูลกลุ่มยังไม่พอ"
        )

        missing.append(
            "รอข้อมูลกลุ่มหุ้นให้พร้อม"
        )

    if catalyst == "positive":
        score += min(
            10,
            max(
                3,
                round(
                    (
                        catalyst_score
                        - 50
                    ) / 3
                )
            )
        )

        checks.append(
            f"🟢 Catalyst เป็นบวก "
            f"({round(catalyst_score)}/100)"
        )

    elif catalyst == "negative":
        score -= min(
            20,
            max(
                8,
                round(
                    (
                        50
                        - catalyst_score
                    ) / 2
                )
            )
        )

        checks.append(
            f"🔴 Catalyst เป็นลบ "
            f"({round(catalyst_score)}/100)"
        )

        missing.append(
            "รอ Catalyst ลบคลี่คลาย "
            "หรือมีข่าวใหม่ยืนยัน"
        )

    elif catalyst == "neutral":
        checks.append(
            "⚪ Catalyst ยังกลาง"
        )

        missing.append(
            "Catalyst บวก "
            "จะช่วยเพิ่มความมั่นใจ"
        )

    else:
        checks.append(
            "⚪ ข่าวยังไม่พร้อม"
        )

        missing.append(
            "รอ Catalyst/ข่าวให้พร้อม"
        )

    score += gate_adjustment
    checks.extend(
        gate_checks
    )

    score = round(
        _clamp(score)
    )

    if gate_block:
        return done(
            "BLOCK",
            score,
            "🔴 งดเข้า",
            (
                "Premarket ต่ำกว่า -5% — "
                "Gate บล็อกการเข้าใหม่จนกว่าจะฟื้น"
            ),
            checks,
            [
                "รอ Premarket ฟื้นเหนือ -5% "
                "และประเมินราคาใหม่"
            ]
        )

    if gate_hot:
        return done(
            "DONT_CHASE",
            score,
            "🟠 ไม่ไล่ราคา",
            (
                "Premarket ตั้งแต่ +5% ขึ้นไป — "
                "Gap-up ร้อนเกินไปสำหรับการไล่เข้า"
            ),
            checks,
            [
                "รอ Pullback / ฐานราคาใหม่ "
                "แล้วประเมินอีกครั้ง"
            ]
        )

    if negative_high_impact:
        return done(
            "BLOCK",
            score,
            "🔴 งดเข้า",
            (
                "พบข่าวลบ Impact สูง — "
                "รอให้ตลาดย่อยข่าวก่อน"
            ),
            checks,
            [
                "รอผลกระทบจากข่าวลบ "
                "Impact สูงคลี่คลาย"
            ]
        )

    if (
        market == "bear"
        and sector == "bear"
    ):
        return done(
            "BLOCK",
            score,
            "🔴 งดเข้า",
            (
                "ภาพรวม Watchlist "
                "และกลุ่มหุ้นอ่อนพร้อมกัน"
            ),
            checks,
            missing
        )

    if price > hi:
        return done(
            "DONT_CHASE",
            score,
            "🟠 ไม่ไล่ราคา",
            "ราคาสูงกว่า Buy Zone",
            checks,
            missing
        )

    if price < lo:
        return done(
            "WAIT",
            score,
            "🟡 เฝ้ารอ Trigger",
            (
                "ราคายังต่ำกว่า Buy Zone — "
                "ยังไม่ใช่จังหวะเข้าไม้ 1"
            ),
            checks,
            missing
        )

    if premarket_pct is None:
        missing.insert(
            0,
            (
                "ใส่ % Premarket จาก Webull "
                "เพื่อผ่าน Premarket Gate"
            )
        )

        return done(
            "WAIT",
            score,
            "🟡 รอ % Premarket",
            (
                "เงื่อนไขหลักอาจดี "
                "แต่ยังไม่มี % Premarket "
                "สำหรับยืนยัน Gate"
            ),
            checks,
            missing
        )

    if score >= 80:
        return done(
            "CONFIRMED",
            score,
            "🟢 เข้าไม้ 1",
            (
                "ราคาอยู่ใน Buy Zone "
                "และ Decision Engine + "
                "Premarket Gate ผ่านเกณฑ์"
            ),
            checks,
            []
        )

    if score >= 64:
        return done(
            "WAIT",
            score,
            "🟡 เฝ้ารอ Trigger",
            (
                "ราคาอยู่ใน Buy Zone "
                "แต่ Context ยังไม่แข็งแรงพอ "
                "สำหรับไฟเขียว"
            ),
            checks,
            missing
        )

    return done(
        "WAIT",
        score,
        "🟡 เฝ้ารอ Trigger",
        (
            "Decision Engine "
            "ยังไม่ผ่านเกณฑ์เข้าไม้ 1"
        ),
        checks,
        missing
    )


def scanner_home():
    return render_template(
        "scanner.html",
        watchlist=load_json(
            "watchlist.json"
        )
    )


app.view_functions["home"] = (
    scanner_home
)


@app.route("/scanner")
def scanner_page():
    return scanner_home()


@app.route("/api/scan")
def api_scan():
    try:
        return jsonify({
            "ok": True,
            "data": scan_watchlist(
                False
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 200


@app.route("/api/scan/refresh")
def api_scan_refresh():
    try:
        return jsonify({
            "ok": True,
            "data": scan_watchlist(
                True
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 200


@app.route("/api/top-picks")
def top_picks():
    try:
        force = (
            request.args.get("force")
            == "1"
        )

        return jsonify({
            "ok": True,
            "data": build_top_picks(
                force
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 200


@app.route("/api/catalyst/<ticker>")
def catalyst(ticker):
    try:
        return jsonify({
            "ok": True,
            "data": _get_catalyst(
                ticker.upper(),
                request.args.get(
                    "force"
                ) == "1"
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 200


@app.route(
    "/api/auto-confirm",
    methods=["POST"]
)
def auto_confirm():
    try:
        return jsonify({
            "ok": True,
            "data": _auto_confirm(
                request.get_json(
                    silent=True
                )
                or {}
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )


# ============================================================
# AI MARKET RADAR V4.6
# Opening Confirmation Engine
#
# เพิ่มต่อจาก V4.5.2 โดยไม่แก้ Premarket Gate เดิม
#
# Workflow:
# PREMARKET -> WATCH -> OPENING CHECK -> ARMED -> ENTRY 1
#
# ใช้ข้อมูลจาก Webull แบบ Manual / Free-first
# ============================================================


def _opening_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _opening_clamp(value):
    return max(0, min(100, value))


def _opening_confirmation(p):
    """
    V4.6 Opening Confirmation Engine

    Required:
    - price             ราคาปัจจุบัน
    - open_price        ราคาเปิดตลาด
    - opening_high      High ของ Opening Range
    - opening_low       Low ของ Opening Range
    - buy_low
    - buy_high
    - stop
    - tp1

    Optional:
    - premarket_pct
    - rel_volume
    - market
    - sector
    - catalyst
    - catalyst_score
    - negative_high_impact

    แนวคิด:
    - Premarket HOT ไม่ได้แปลว่าโดนตัดทิ้งทั้งวัน
    - หลังตลาดเปิด หุ้น HOT สามารถกลับมา ARMED ได้
      ถ้าราคาสร้างฐาน / Pullback รับอยู่ / Momentum ยืนยัน
    - Catalyst บวกช่วยได้ แต่ไม่ Override Chase Protection
    """

    price = _opening_float(p.get("price"))
    open_price = _opening_float(p.get("open_price"))
    opening_high = _opening_float(p.get("opening_high"))
    opening_low = _opening_float(p.get("opening_low"))

    buy_low = _opening_float(p.get("buy_low"))
    buy_high = _opening_float(p.get("buy_high"))
    stop = _opening_float(p.get("stop"))
    tp1 = _opening_float(p.get("tp1"))

    premarket_pct = _opening_float(
        p.get("premarket_pct")
    )

    rel_volume = _opening_float(
        p.get("rel_volume")
    )

    market = p.get(
        "market",
        "unknown"
    )

    sector = p.get(
        "sector",
        "unknown"
    )

    catalyst = p.get(
        "catalyst",
        "unknown"
    )

    catalyst_score = _opening_float(
        p.get("catalyst_score"),
        50
    )

    negative_high_impact = bool(
        p.get("negative_high_impact")
    )

    confidence = p.get(
        "data_confidence",
        "FRESH"
    )

    required = {
        "price": price,
        "open_price": open_price,
        "opening_high": opening_high,
        "opening_low": opening_low,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "stop": stop,
        "tp1": tp1
    }

    missing_fields = [
        k
        for k, v in required.items()
        if v is None
    ]

    if missing_fields:
        return {
            "status": "INCOMPLETE",
            "state": "WATCH",
            "score": 0,
            "label": "⚪ Opening Check ยังไม่ครบ",
            "reason": (
                "กรอกข้อมูล Opening Range ให้ครบก่อน"
            ),
            "checks": [
                "⚪ ข้อมูลยังไม่ครบ: "
                + ", ".join(missing_fields)
            ],
            "next_step": (
                "ใส่ราคาเปิด, Opening High/Low "
                "และราคาปัจจุบันจาก Webull"
            )
        }

    if opening_low > opening_high:
        return {
            "status": "INVALID",
            "state": "WATCH",
            "score": 0,
            "label": "⚪ ข้อมูล Opening Range ผิด",
            "reason": (
                "Opening Low สูงกว่า Opening High"
            ),
            "checks": [
                "⚪ ตรวจตัวเลข Opening High / Low อีกครั้ง"
            ],
            "next_step": (
                "แก้ Opening Range แล้วตรวจใหม่"
            )
        }

    checks = []
    score = 50

    opening_mid = (
        opening_high + opening_low
    ) / 2

    change_from_open = (
        (price / open_price - 1) * 100
        if open_price > 0
        else 0
    )

    range_pct = (
        (
            opening_high
            - opening_low
        )
        / open_price
        * 100
        if open_price > 0
        else 0
    )

    hot_premarket = (
        premarket_pct is not None
        and premarket_pct >= 5
    )

    # --------------------------------------------------------
    # HARD INVALIDATION
    # --------------------------------------------------------

    if confidence == "CACHED":
        return {
            "status": "BLOCK",
            "state": "INVALIDATED",
            "score": 0,
            "label": "🔴 INVALIDATED",
            "reason": (
                "ข้อมูลหุ้นยังเป็น Cache"
            ),
            "checks": [
                "🔴 ต้อง Refresh ข้อมูลก่อนใช้ Opening Check"
            ],
            "next_step": (
                "รีเฟรช Scanner ให้ข้อมูลเป็น Fresh/Recovered"
            )
        }

    if price < stop:
        return {
            "status": "BLOCK",
            "state": "INVALIDATED",
            "score": 0,
            "label": "🔴 INVALIDATED",
            "reason": (
                "ราคาหลุด Stop / แผนเดิมผิด"
            ),
            "checks": [
                "🔴 ราคาต่ำกว่า Stop"
            ],
            "next_step": (
                "ไม่เข้าใหม่ รอสร้าง Setup ใหม่"
            )
        }

    if negative_high_impact:
        return {
            "status": "BLOCK",
            "state": "INVALIDATED",
            "score": 20,
            "label": "🔴 INVALIDATED",
            "reason": (
                "มีข่าวลบ Impact สูง"
            ),
            "checks": [
                "🔴 Catalyst Risk ยังไม่คลี่คลาย"
            ],
            "next_step": (
                "รอให้ตลาดย่อยข่าวและประเมินใหม่"
            )
        }

    if (
        market == "bear"
        and sector == "bear"
    ):
        return {
            "status": "BLOCK",
            "state": "WATCH",
            "score": 25,
            "label": "🔴 ยังไม่เข้า",
            "reason": (
                "Market + Group อ่อนพร้อมกัน"
            ),
            "checks": [
                "🔴 ภาพรวมตลาดและกลุ่มยังไม่สนับสนุน"
            ],
            "next_step": (
                "รอ Market/Group ฟื้นก่อน"
            )
        }

    if price >= tp1:
        return {
            "status": "DONT_CHASE",
            "state": "WATCH",
            "score": 20,
            "label": "🟠 ไม่ไล่ราคา",
            "reason": (
                "ราคาถึงหรือเกิน TP1 แล้ว"
            ),
            "checks": [
                "🟠 Risk/Reward ไม่เหมาะกับ Entry ใหม่"
            ],
            "next_step": (
                "รอ Setup / Buy Zone ใหม่"
            )
        }

    # --------------------------------------------------------
    # PRICE STRUCTURE
    # --------------------------------------------------------

    if buy_low <= price <= buy_high:
        score += 18

        checks.append(
            "🟢 ราคาปัจจุบันอยู่ใน Buy Zone"
        )

    elif price < buy_low:
        score -= 8

        checks.append(
            "🟡 ราคายังต่ำกว่า Buy Zone"
        )

    else:
        score -= 15

        checks.append(
            "🟠 ราคาเหนือ Buy Zone — ไม่ไล่"
        )

    # --------------------------------------------------------
    # OPENING RANGE STRUCTURE
    # --------------------------------------------------------

    if price < opening_low:
        score -= 24

        checks.append(
            "🔴 ราคาหลุด Opening Low"
        )

    elif price >= opening_mid:
        score += 12

        checks.append(
            "🟢 ราคายืนเหนือกึ่งกลาง Opening Range"
        )

    else:
        score -= 5

        checks.append(
            "🟡 ราคาอยู่ครึ่งล่างของ Opening Range"
        )

    # ราคาเทียบราคาเปิด
    if price >= open_price:
        score += 8

        checks.append(
            "🟢 ราคายืนเหนือราคาเปิด"
        )

    else:
        score -= 6

        checks.append(
            "🟡 ราคายังต่ำกว่าราคาเปิด"
        )

    # --------------------------------------------------------
    # OPENING RANGE WIDTH
    # --------------------------------------------------------

    if range_pct >= 5:
        score -= 7

        checks.append(
            "🟡 Opening Range กว้างมาก "
            "ความผันผวนสูง"
        )

    elif range_pct <= 2.5:
        score += 4

        checks.append(
            "🟢 Opening Range ไม่กว้างเกินไป"
        )

    else:
        checks.append(
            "⚪ Opening Range อยู่ระดับกลาง"
        )

    # --------------------------------------------------------
    # RELATIVE VOLUME
    # --------------------------------------------------------

    if rel_volume is None:
        checks.append(
            "⚪ Relative Volume ไม่ได้กรอก — "
            "ไม่หักคะแนน"
        )

    elif rel_volume >= 1.2 and rel_volume <= 3:
        score += 9

        checks.append(
            "🟢 Relative Volume ยืนยันแรงซื้อ"
        )

    elif rel_volume > 3:
        score += 4

        checks.append(
            "🟡 Relative Volume สูงมาก "
            "Momentum แรงแต่ผันผวน"
        )

    elif rel_volume < 0.8:
        score -= 6

        checks.append(
            "🟡 Volume ยังไม่ยืนยัน"
        )

    else:
        checks.append(
            "⚪ Relative Volume ระดับกลาง"
        )

    # --------------------------------------------------------
    # MARKET / GROUP CONTEXT
    # --------------------------------------------------------

    if market == "bull":
        score += 7

        checks.append(
            "🟢 Market Context สนับสนุน"
        )

    elif market == "bear":
        score -= 9

        checks.append(
            "🔴 Market Context อ่อน"
        )

    else:
        checks.append(
            "⚪ Market Context กลาง"
        )

    if sector == "bull":
        score += 7

        checks.append(
            "🟢 Group Context สนับสนุน"
        )

    elif sector == "bear":
        score -= 9

        checks.append(
            "🔴 Group Context อ่อน"
        )

    else:
        checks.append(
            "⚪ Group Context กลาง"
        )

    # --------------------------------------------------------
    # CATALYST
    # Catalyst ช่วย Priority ได้
    # แต่ไม่สามารถยกเลิก Stop / Chase Protection
    # --------------------------------------------------------

    if catalyst == "positive":
        catalyst_bonus = min(
            7,
            max(
                2,
                round(
                    (
                        catalyst_score
                        - 50
                    ) / 5
                )
            )
        )

        score += catalyst_bonus

        checks.append(
            f"🟢 Positive Catalyst "
            f"({round(catalyst_score)}/100)"
        )

    elif catalyst == "negative":
        score -= 8

        checks.append(
            "🔴 Catalyst เชิงลบ"
        )

    else:
        checks.append(
            "⚪ Catalyst ยังไม่ชัด"
        )

    # --------------------------------------------------------
    # PREMARKET HOT RECOVERY LOGIC
    #
    # จุดสำคัญของ V4.6:
    # +5% ขึ้นไปไม่ถูกตัดทิ้งทั้งวัน
    #
    # แต่ต้องมี Opening Confirmation เพิ่ม
    # --------------------------------------------------------

    if hot_premarket:
        checks.append(
            f"🟠 Premarket HOT "
            f"{premarket_pct:+.2f}%"
        )

        hot_recovered = (
            price >= open_price
            and price >= opening_mid
            and buy_low <= price <= buy_high
        )

        strong_volume = (
            rel_volume is not None
            and rel_volume >= 1.2
        )

        if hot_recovered:
            checks.append(
                "🟢 Gap-up เริ่มสร้างฐาน "
                "และยืนเหนือ Opening Mid"
            )

            # HOT stock ต้องการ Volume มากกว่าหุ้นปกติ
            if strong_volume:
                score += 5

                checks.append(
                    "🟢 HOT Gap มี Volume สนับสนุน"
                )

            else:
                score -= 7

                checks.append(
                    "🟡 HOT Gap ยังขาด Volume ยืนยัน"
                )

        else:
            score -= 15

            checks.append(
                "🟠 HOT Gap ยังไม่สร้างฐานที่ดีพอ"
            )

    score = round(
        _opening_clamp(score)
    )

    # --------------------------------------------------------
    # STATE MACHINE
    # --------------------------------------------------------

    # หลุด Opening Low
    if price < opening_low:
        return {
            "status": "WAIT",
            "state": "WATCH",
            "score": score,
            "label": "🟡 WATCH",
            "reason": (
                "ราคาหลุด Opening Low "
                "ยังไม่ผ่าน Opening Confirmation"
            ),
            "checks": checks,
            "next_step": (
                "รอราคากลับเหนือ Opening Low "
                "และ Opening Mid ก่อนตรวจใหม่"
            ),
            "opening": {
                "open": open_price,
                "high": opening_high,
                "low": opening_low,
                "mid": round(opening_mid, 2),
                "change_from_open_pct": round(
                    change_from_open,
                    2
                ),
                "range_pct": round(
                    range_pct,
                    2
                )
            }
        }

    # ราคาเหนือ Buy Zone
    if price > buy_high:
        return {
            "status": "DONT_CHASE",
            "state": "WATCH",
            "score": score,
            "label": "🟠 ไม่ไล่ราคา",
            "reason": (
                "Opening Structure อาจดี "
                "แต่ราคาเหนือ Buy Zone"
            ),
            "checks": checks,
            "next_step": (
                f"รอ Pullback กลับ ≤ "
                f"${buy_high:.2f}"
            ),
            "opening": {
                "open": open_price,
                "high": opening_high,
                "low": opening_low,
                "mid": round(opening_mid, 2),
                "change_from_open_pct": round(
                    change_from_open,
                    2
                ),
                "range_pct": round(
                    range_pct,
                    2
                )
            }
        }

    # ต่ำกว่า Buy Zone
    if price < buy_low:
        return {
            "status": "WAIT",
            "state": "WATCH",
            "score": score,
            "label": "🟡 WATCH",
            "reason": (
                "ราคายังต่ำกว่า Buy Zone"
            ),
            "checks": checks,
            "next_step": (
                f"รอราคากลับ ≥ "
                f"${buy_low:.2f}"
            ),
            "opening": {
                "open": open_price,
                "high": opening_high,
                "low": opening_low,
                "mid": round(opening_mid, 2),
                "change_from_open_pct": round(
                    change_from_open,
                    2
                ),
                "range_pct": round(
                    range_pct,
                    2
                )
            }
        }

    # HOT Premarket ต้องเข้มกว่า
    if hot_premarket:
        hot_ready = (
            price >= open_price
            and price >= opening_mid
            and (
                rel_volume is None
                or rel_volume >= 1.0
            )
        )

        if not hot_ready:
            return {
                "status": "WAIT",
                "state": "WATCH",
                "score": score,
                "label": "🟡 WATCH",
                "reason": (
                    "Premarket HOT "
                    "แต่ Opening Confirmation "
                    "ยังไม่แข็งแรงพอ"
                ),
                "checks": checks,
                "next_step": (
                    "รอให้ราคายืนเหนือ Open + "
                    "Opening Mid และดู Volume ยืนยัน"
                ),
                "opening": {
                    "open": open_price,
                    "high": opening_high,
                    "low": opening_low,
                    "mid": round(
                        opening_mid,
                        2
                    ),
                    "change_from_open_pct": round(
                        change_from_open,
                        2
                    ),
                    "range_pct": round(
                        range_pct,
                        2
                    )
                }
            }

    # --------------------------------------------------------
    # FINAL STATE
    # --------------------------------------------------------

    if score >= 82:
        return {
            "status": "CONFIRMED",
            "state": "ENTRY1",
            "score": score,
            "label": "🟢 ENTRY 1",
            "reason": (
                "ราคาอยู่ใน Buy Zone "
                "และ Opening Structure ผ่าน"
            ),
            "checks": checks,
            "next_step": (
                "เข้าไม้ 1 ตามแผน "
                "และใช้ Stop เดิมเป็น Invalidation"
            ),
            "opening": {
                "open": open_price,
                "high": opening_high,
                "low": opening_low,
                "mid": round(
                    opening_mid,
                    2
                ),
                "change_from_open_pct": round(
                    change_from_open,
                    2
                ),
                "range_pct": round(
                    range_pct,
                    2
                )
            }
        }

    if score >= 68:
        return {
            "status": "ARMED",
            "state": "ARMED",
            "score": score,
            "label": "🟦 ARMED",
            "reason": (
                "Setup ดีขึ้นและใกล้พร้อม "
                "แต่ยังต้องการ Confirmation เพิ่ม"
            ),
            "checks": checks,
            "next_step": (
                "เฝ้าราคายืนเหนือ Opening Mid/Open "
                "และ Volume ไม่อ่อนลง"
            ),
            "opening": {
                "open": open_price,
                "high": opening_high,
                "low": opening_low,
                "mid": round(
                    opening_mid,
                    2
                ),
                "change_from_open_pct": round(
                    change_from_open,
                    2
                ),
                "range_pct": round(
                    range_pct,
                    2
                )
            }
        }

    return {
        "status": "WAIT",
        "state": "WATCH",
        "score": score,
        "label": "🟡 WATCH",
        "reason": (
            "Opening Confirmation "
            "ยังไม่ผ่านเกณฑ์"
        ),
        "checks": checks,
        "next_step": (
            "รอ Structure / Context / Volume "
            "ดีขึ้นแล้วตรวจใหม่"
        ),
        "opening": {
            "open": open_price,
            "high": opening_high,
            "low": opening_low,
            "mid": round(
                opening_mid,
                2
            ),
            "change_from_open_pct": round(
                change_from_open,
                2
            ),
            "range_pct": round(
                range_pct,
                2
            )
        }
    }


@app.route(
    "/api/opening-confirm",
    methods=["POST"]
)
def opening_confirm():
    try:
        payload = (
            request.get_json(
                silent=True
            )
            or {}
        )

        return jsonify({
            "ok": True,
            "version": "4.6",
            "data": _opening_confirmation(
                payload
            )
        }), 200

    except Exception as e:
        return jsonify({
            "ok": False,
            "version": "4.6",
            "error": str(e)
        }), 200
# ============================================================
# AI MARKET RADAR V4.7
# POSITION ENGINE
#
# Append-only extension for V4.6
#
# Workflow:
# WATCH -> HOLD -> ADD ARMED -> ADD
#       -> TAKE PROFIT
#       -> INVALIDATED
#
# Core rules:
# - Having a position prevents repeated "ENTRY 1" instructions
# - Falling price alone NEVER unlocks ADD
# - ADD needs reclaim + Opening Confirmation
# - Price below average cost = no automatic averaging down
# - Stop is not moved lower automatically
# ============================================================


def _position_float(value, default=None):
    try:
        if value in (None, ""):
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _position_clamp(value):
    return max(
        0,
        min(
            100,
            value
        )
    )


def _position_manage(p):

    ticker = str(
        p.get("ticker")
        or ""
    ).upper().strip()


    # --------------------------------------------------------
    # POSITION DATA
    # --------------------------------------------------------

    shares = _position_float(
        p.get("shares")
    )

    avg_cost = _position_float(
        p.get("avg_cost")
    )

    price = _position_float(
        p.get("price")
    )


    # --------------------------------------------------------
    # PLAN LEVELS
    # --------------------------------------------------------

    buy_low = _position_float(
        p.get("buy_low")
    )

    buy_high = _position_float(
        p.get("buy_high")
    )

    stop = _position_float(
        p.get("stop")
    )

    tp1 = _position_float(
        p.get("tp1")
    )

    tp2 = _position_float(
        p.get("tp2")
    )


    # --------------------------------------------------------
    # OPTIONAL POSITION SIZE GUARD
    # --------------------------------------------------------

    max_position_value = _position_float(
        p.get("max_position_value")
    )


    # --------------------------------------------------------
    # OPENING CONFIRMATION
    # --------------------------------------------------------

    opening_state = str(
        p.get("opening_state")
        or "UNKNOWN"
    ).upper()

    opening_score = _position_float(
        p.get("opening_score"),
        0
    )

    open_price = _position_float(
        p.get("open_price")
    )

    opening_mid = _position_float(
        p.get("opening_mid")
    )

    opening_low = _position_float(
        p.get("opening_low")
    )


    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    market = str(
        p.get("market")
        or "unknown"
    ).lower()

    sector = str(
        p.get("sector")
        or "unknown"
    ).lower()

    catalyst = str(
        p.get("catalyst")
        or "unknown"
    ).lower()

    catalyst_score = _position_float(
        p.get("catalyst_score"),
        50
    )

    negative_high_impact = bool(
        p.get(
            "negative_high_impact"
        )
    )

    confidence = str(
        p.get("data_confidence")
        or "FRESH"
    ).upper()


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    required = {
        "shares": shares,
        "avg_cost": avg_cost,
        "price": price,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "stop": stop,
        "tp1": tp1
    }


    missing = [
        key
        for key, value
        in required.items()
        if value is None
    ]


    if missing:

        return {
            "status": "INCOMPLETE",
            "state": "WATCH",
            "action": "WAIT",
            "score": 0,
            "add_allowed": False,

            "label":
                "⚪ Position ข้อมูลยังไม่ครบ",

            "reason":
                "กรอกข้อมูล Position ให้ครบก่อน",

            "checks": [
                "⚪ ข้อมูลยังไม่ครบ: "
                + ", ".join(missing)
            ],

            "next_step":
                "ใส่ Shares, Average Cost "
                "และ Current Price"
        }


    if shares <= 0:

        return {
            "status": "NO_POSITION",
            "state": "WATCH",
            "action": "WAIT",
            "score": 0,
            "add_allowed": False,

            "label":
                "⚪ ยังไม่มี Position",

            "reason":
                "Shares ต้องมากกว่า 0 "
                "จึงจะใช้ Position Engine",

            "checks": [
                "⚪ Shares = 0"
            ],

            "next_step":
                "หุ้นที่ยังไม่ได้ถือ "
                "ให้ใช้ Premarket Gate + "
                "Opening Confirmation"
        }


    if (
        avg_cost <= 0
        or price <= 0
        or buy_low <= 0
        or buy_high <= 0
        or stop <= 0
        or tp1 <= 0
    ):

        return {
            "status": "INVALID",
            "state": "WATCH",
            "action": "WAIT",
            "score": 0,
            "add_allowed": False,

            "label":
                "⚪ Position ข้อมูลไม่ถูกต้อง",

            "reason":
                "ราคาและจำนวนต้องมากกว่า 0",

            "checks": [
                "⚪ ตรวจตัวเลขอีกครั้ง"
            ],

            "next_step":
                "แก้ข้อมูลแล้วตรวจใหม่"
        }


    if buy_low > buy_high:

        return {
            "status": "INVALID",
            "state": "WATCH",
            "action": "WAIT",
            "score": 0,
            "add_allowed": False,

            "label":
                "⚪ Buy Zone ไม่ถูกต้อง",

            "reason":
                "Buy Low สูงกว่า Buy High",

            "checks": [
                "⚪ Refresh Scanner "
                "แล้วตรวจ Buy Zone ใหม่"
            ],

            "next_step":
                "ตรวจ Buy Zone ใหม่"
        }


    # --------------------------------------------------------
    # POSITION METRICS
    # --------------------------------------------------------

    position_value = (
        price
        * shares
    )

    cost_value = (
        avg_cost
        * shares
    )

    pnl_usd = (
        price
        - avg_cost
    ) * shares

    pnl_pct = (
        (
            price
            / avg_cost
            - 1
        )
        * 100
    )


    risk_to_stop_usd = max(
        0,
        (
            avg_cost
            - stop
        )
        * shares
    )


    upside_to_tp1_pct = (
        (
            tp1
            / price
            - 1
        )
        * 100
    )


    # --------------------------------------------------------
    # POSITION SIZE GUARD
    # --------------------------------------------------------

    guard_configured = (
        max_position_value is not None
        and max_position_value > 0
    )


    remaining_budget = None
    guard_block = False


    if guard_configured:

        remaining_budget = max(
            0,
            max_position_value
            - position_value
        )

        guard_block = (
            position_value
            >= max_position_value
        )


    # --------------------------------------------------------
    # ADD TRIGGER
    #
    # ต้อง reclaim อย่างน้อย:
    # Buy Low + Average Cost
    #
    # ถ้ามี Opening data:
    # Open + Opening Mid จะถูกใช้ด้วย
    # --------------------------------------------------------

    trigger_candidates = [
        buy_low,
        avg_cost
    ]


    if (
        open_price is not None
        and open_price > 0
    ):

        trigger_candidates.append(
            open_price
        )


    if (
        opening_mid is not None
        and opening_mid > 0
    ):

        trigger_candidates.append(
            opening_mid
        )


    add_trigger = max(
        trigger_candidates
    )


    trigger_inside_zone = (
        add_trigger
        <= buy_high
    )


    # --------------------------------------------------------
    # POSITION SCORE
    # --------------------------------------------------------

    score = 50
    checks = []


    # Data freshness

    if confidence == "CACHED":

        score -= 25

        checks.append(
            "🔴 ข้อมูล Scanner เป็น Cache"
        )


    elif confidence == "RECOVERED":

        score += 2

        checks.append(
            "🟡 ข้อมูล Scanner เป็น Recovered"
        )


    else:

        score += 5

        checks.append(
            "🟢 ข้อมูล Scanner Fresh"
        )


    # P/L

    if pnl_pct >= 0:

        score += 6

        checks.append(
            f"🟢 Position บวก "
            f"{pnl_pct:+.2f}%"
        )


    else:

        score -= 4

        checks.append(
            f"🟡 Position ติดลบ "
            f"{pnl_pct:+.2f}%"
        )


    # Buy Zone

    if (
        buy_low
        <= price
        <= buy_high
    ):

        score += 10

        checks.append(
            "🟢 ราคาอยู่ใน Buy Zone"
        )


    elif price < buy_low:

        score -= 10

        checks.append(
            "🟡 ราคาต่ำกว่า Buy Zone — "
            "ไม่ถัวเพราะราคาลงอย่างเดียว"
        )


    else:

        score -= 8

        checks.append(
            "🟠 ราคาเหนือ Buy Zone — "
            "ไม่ไล่เพิ่ม"
        )


    # Opening Confirmation

    if opening_state == "ENTRY1":

        score += 18

        checks.append(
            "🟢 Opening Confirmation "
            "= ENTRY 1"
        )


    elif opening_state == "ARMED":

        score += 10

        checks.append(
            "🟦 Opening Confirmation "
            "= ARMED"
        )


    elif opening_state == "INVALIDATED":

        score -= 25

        checks.append(
            "🔴 Opening Setup "
            "ถูก Invalidated"
        )


    else:

        score -= 8

        checks.append(
            "🟡 Opening Confirmation "
            "ยังเป็น WATCH/ยังไม่ได้ตรวจ"
        )


    # Market

    if market == "bull":

        score += 6

        checks.append(
            "🟢 Market Context สนับสนุน"
        )


    elif market == "bear":

        score -= 8

        checks.append(
            "🔴 Market Context อ่อน"
        )


    else:

        checks.append(
            "⚪ Market Context กลาง"
        )


    # Group

    if sector == "bull":

        score += 6

        checks.append(
            "🟢 Group Context สนับสนุน"
        )


    elif sector == "bear":

        score -= 8

        checks.append(
            "🔴 Group Context อ่อน"
        )


    else:

        checks.append(
            "⚪ Group Context กลาง"
        )


    # Catalyst

    if catalyst == "positive":

        catalyst_bonus = min(
            5,
            max(
                1,
                round(
                    (
                        catalyst_score
                        - 50
                    )
                    / 8
                )
            )
        )

        score += catalyst_bonus

        checks.append(
            f"🟢 Catalyst บวก "
            f"({round(catalyst_score)}/100)"
        )


    elif catalyst == "negative":

        score -= 7

        checks.append(
            "🔴 Catalyst เป็นลบ"
        )


    else:

        checks.append(
            "⚪ Catalyst ยังไม่ชัด"
        )


    # Size Guard

    if guard_configured:

        if guard_block:

            score -= 12

            checks.append(
                "🔴 Position Size Guard "
                "ถึงงบสูงสุดแล้ว"
            )

        else:

            checks.append(
                "🟢 Position Size Guard "
                "ยังมี Headroom"
            )


    else:

        checks.append(
            "⚪ ยังไม่ได้ตั้งงบสูงสุด "
            "ของ Position"
        )


    score = round(
        _position_clamp(
            score
        )
    )


    # --------------------------------------------------------
    # BASE RESPONSE
    # --------------------------------------------------------

    base = {

        "ticker": ticker,

        "score": score,

        "checks": checks,


        "position": {

            "shares":
                shares,

            "avg_cost":
                round(
                    avg_cost,
                    4
                ),

            "price":
                round(
                    price,
                    4
                ),

            "market_value":
                round(
                    position_value,
                    2
                ),

            "cost_value":
                round(
                    cost_value,
                    2
                ),

            "pnl_usd":
                round(
                    pnl_usd,
                    2
                ),

            "pnl_pct":
                round(
                    pnl_pct,
                    2
                ),

            "risk_to_stop_usd":
                round(
                    risk_to_stop_usd,
                    2
                ),

            "upside_to_tp1_pct":
                round(
                    upside_to_tp1_pct,
                    2
                )
        },


        "levels": {

            "buy_low":
                buy_low,

            "buy_high":
                buy_high,

            "add_trigger":
                round(
                    add_trigger,
                    4
                ),

            "stop":
                stop,

            "tp1":
                tp1,

            "tp2":
                tp2
        },


        "guard": {

            "configured":
                guard_configured,

            "max_position_value":
                (
                    round(
                        max_position_value,
                        2
                    )
                    if guard_configured
                    else None
                ),

            "remaining_budget":
                (
                    round(
                        remaining_budget,
                        2
                    )
                    if remaining_budget
                    is not None
                    else None
                ),

            "blocked":
                guard_block
        },


        "opening": {

            "state":
                opening_state,

            "score":
                round(
                    opening_score
                    or 0
                ),

            "open":
                open_price,

            "mid":
                opening_mid,

            "low":
                opening_low
        }
    }


    # ========================================================
    # HARD INVALIDATION
    # ========================================================

    if price <= stop:

        return {
            **base,

            "status":
                "INVALIDATED",

            "state":
                "INVALIDATED",

            "action":
                "EXIT",

            "add_allowed":
                False,

            "label":
                "🔴 INVALIDATED / EXIT PLAN",

            "reason":
                "ราคาถึงหรือต่ำกว่า Stop "
                "ของแผนเดิม",

            "next_step":
                "ห้าม ADD และใช้ Stop/Exit "
                "ตามแผนเดิม "
                "ไม่ขยับ Stop ลง"
        }


    # ========================================================
    # DATA NOT FRESH
    # ========================================================

    if confidence == "CACHED":

        return {
            **base,

            "status":
                "REFRESH",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD / REFRESH DATA",

            "reason":
                "มี Position อยู่ "
                "แต่ Scanner เป็น Cache",

            "next_step":
                "ยังไม่ ADD "
                "จนกว่าจะ Refresh "
                "เป็น Fresh/Recovered"
        }


    # ========================================================
    # NEGATIVE HIGH IMPACT NEWS
    # ========================================================

    if negative_high_impact:

        return {
            **base,

            "status":
                "RISK_REVIEW",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟠 HOLD / RISK REVIEW",

            "reason":
                "มีข่าวลบ Impact สูง "
                "จึงไม่เพิ่ม Position",

            "next_step":
                "ติดตามข่าวและราคาใกล้ Stop "
                "ก่อนตัดสินใจรอบถัดไป"
        }


    # ========================================================
    # TAKE PROFIT
    # ========================================================

    if (
        tp2 is not None
        and tp2 > 0
        and price >= tp2
    ):

        return {
            **base,

            "status":
                "TAKE_PROFIT",

            "state":
                "TAKE_PROFIT",

            "action":
                "TAKE_PROFIT",

            "add_allowed":
                False,

            "label":
                "🟢 TAKE PROFIT • TP2",

            "reason":
                "ราคาถึงหรือสูงกว่า TP2 แล้ว",

            "next_step":
                "ไม่ ADD เพิ่มในจุดนี้ "
                "ให้บริหารกำไรตามแผน"
        }


    if price >= tp1:

        return {
            **base,

            "status":
                "TAKE_PROFIT",

            "state":
                "TAKE_PROFIT",

            "action":
                "TAKE_PROFIT",

            "add_allowed":
                False,

            "label":
                "🟢 TAKE PROFIT • TP1",

            "reason":
                "ราคาถึงหรือสูงกว่า TP1 แล้ว",

            "next_step":
                "ไม่ไล่ ADD ที่ TP1 "
                "ให้บริหารกำไรและดู TP2"
        }


    # ========================================================
    # POSITION SIZE LIMIT
    # ========================================================

    if guard_block:

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD • SIZE LIMIT",

            "reason":
                "Position ถึงงบสูงสุด "
                "ที่ตั้งไว้แล้ว",

            "next_step":
                "ถือ Position เดิม "
                "และไม่เพิ่มจนกว่าจะปรับแผนงบ"
        }


    # ========================================================
    # ABOVE BUY ZONE
    # ========================================================

    if price > buy_high:

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟠 HOLD • DO NOT CHASE",

            "reason":
                "Position เดิมถือได้ตามแผน "
                "แต่ราคาสูงกว่า Buy Zone",

            "next_step":
                f"ไม่ ADD • รอ Pullback ≤ "
                f"${buy_high:.2f} "
                "หรือ Setup ใหม่"
        }


    # ========================================================
    # BELOW BUY ZONE
    # ========================================================

    if price < buy_low:

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD • DO NOT ADD",

            "reason":
                "ราคาต่ำกว่า Buy Zone "
                "จึงไม่ถัวลงอัตโนมัติ",

            "next_step":
                f"รอ Reclaim อย่างน้อย "
                f"${buy_low:.2f} "
                "และ Opening Confirmation ดีขึ้น"
        }


    # ========================================================
    # ADD TRIGGER OUTSIDE BUY ZONE
    # ========================================================

    if not trigger_inside_zone:

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD • WAIT NEW SETUP",

            "reason":
                "ADD Trigger สูงกว่า Buy Zone "
                "จึงไม่เพิ่มไม้ตาม Setup เดิม",

            "next_step":
                "ถือเดิมและรอ Scanner "
                "สร้าง Buy Zone ใหม่"
        }


    # ========================================================
    # OPENING INVALIDATED BUT MAIN STOP STILL HOLDS
    # ========================================================

    if opening_state == "INVALIDATED":

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟠 HOLD • OPENING INVALIDATED",

            "reason":
                "Opening Setup ถูก Invalidated "
                "แต่ราคายังไม่ถึง Stop หลัก",

            "next_step":
                "ไม่ ADD • ถือ/เฝ้าตาม Stop เดิม "
                "และรอ Setup ใหม่"
        }


    # ========================================================
    # OPENING NOT READY
    # ========================================================

    if opening_state not in (
        "ENTRY1",
        "ARMED"
    ):

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD • WAIT CONFIRMATION",

            "reason":
                "มี Position แล้ว "
                "แต่ Opening Confirmation "
                "ยังไม่ผ่านสำหรับการเพิ่มไม้",

            "next_step":
                f"ADD Trigger อ้างอิง "
                f"${add_trigger:.2f} "
                "แต่ต้องให้ Opening "
                "เป็น ARMED/ENTRY1 ก่อน"
        }


    # ========================================================
    # NO AUTOMATIC AVERAGE DOWN
    # ========================================================

    if price < avg_cost:

        return {
            **base,

            "status":
                "HOLD",

            "state":
                "HOLD",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟡 HOLD • NO AVERAGE DOWN",

            "reason":
                "ราคายังต่ำกว่า Average Cost "
                "จึงยังไม่เปิด ADD ใน V4.7",

            "next_step":
                f"รอ Reclaim ≥ "
                f"${add_trigger:.2f} "
                "พร้อม Opening Confirmation"
        }


    # ========================================================
    # WAIT FOR ADD TRIGGER
    # ========================================================

    if price < add_trigger:

        return {
            **base,

            "status":
                "ARMED",

            "state":
                "ARMED",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟦 HOLD • ADD ARMED",

            "reason":
                "Opening ดีขึ้น "
                "แต่ราคายังไม่ถึง ADD Trigger",

            "next_step":
                f"เฝ้า Reclaim ≥ "
                f"${add_trigger:.2f} "
                "โดยต้องยังอยู่ใน Buy Zone"
        }


    # ========================================================
    # OPENING ARMED BUT NOT ENTRY1
    # ========================================================

    if opening_state == "ARMED":

        return {
            **base,

            "status":
                "ARMED",

            "state":
                "ARMED",

            "action":
                "HOLD",

            "add_allowed":
                False,

            "label":
                "🟦 HOLD • ADD ARMED",

            "reason":
                "ราคา Reclaim แล้ว "
                "แต่ Opening ยังเป็น ARMED",

            "next_step":
                "รอ Opening Confirmation "
                "เปลี่ยนเป็น ENTRY1 "
                "ก่อนเปิด ADD"
        }


    # ========================================================
    # ADD READY
    # ========================================================

    return {
        **base,

        "status":
            "ADD_READY",

        "state":
            "ADD",

        "action":
            "ADD",

        "add_allowed":
            True,

        "label":
            "🟢 ADD READY",

        "reason":
            "Position อยู่ใน Buy Zone, "
            "ราคาไม่ต่ำกว่า Average Cost "
            "และ Opening Confirmation = ENTRY1",

        "next_step":
            "สามารถพิจารณาเพิ่มไม้ตามงบที่กำหนด "
            "โดยคง Stop เดิม "
            "และไม่ไล่เกิน Buy Zone"
    }


# ------------------------------------------------------------
# API
# ------------------------------------------------------------

@app.route(
    "/api/position-manage",
    methods=["POST"]
)
def position_manage():

    try:

        payload = (
            request.get_json(
                silent=True
            )
            or {}
        )

        return jsonify({
            "ok": True,
            "version": "4.7",
            "data": _position_manage(
                payload
            )
        }), 200


    except Exception as e:

        return jsonify({
            "ok": False,
            "version": "4.7",
            "error": str(e)
        }), 200
