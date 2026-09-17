"""
AI MARKET RADAR V4.9

Explosive Movers Radar on top of V4.8.2.

Purpose:
- keep the normal Top Pick engine for higher-quality AI / tech setups
- add a SEPARATE radar for RETO-like small-cap momentum / squeeze events
- rank abnormal price + volume behavior without calling it a buy signal

This layer intentionally does not mix Explosive Score into Top Pick Watch Score.
"""

import time
from flask import jsonify, request
import yfinance as yf

import scanner_v482 as v482
import scanner as base

app = v482.app

_EXPLOSIVE_CACHE = {"ts": 0.0, "data": None}
_EXPLOSIVE_TTL = 5 * 60


def _num(v, default=None):
    try:
        if isinstance(v, dict):
            v = v.get("raw", v.get("value"))
        if v in (None, ""):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _extract_quotes(raw):
    if not isinstance(raw, dict):
        return []

    q = raw.get("quotes")
    if isinstance(q, list):
        return q

    try:
        r = raw.get("finance", {}).get("result", [])
        if r and isinstance(r[0], dict):
            q = r[0].get("quotes")
            if isinstance(q, list):
                return q
    except Exception:
        pass

    return []


def _screen_candidates():
    """Use Yahoo's equity screener to discover US small/mid-cap movers."""
    errors = []
    quotes = []

    try:
        EquityQuery = yf.EquityQuery
        q = EquityQuery("and", [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("gte", ["intradayprice", 0.20]),
            EquityQuery("gt", ["dayvolume", 100000]),
            EquityQuery("gt", ["percentchange", 0.50]),
            EquityQuery("gte", ["intradaymarketcap", 15000000]),
            EquityQuery("lt", ["intradaymarketcap", 5000000000]),
        ])

        # One pass catches price leaders, another catches ignition by raw volume.
        for sort_field in ("percentchange", "dayvolume"):
            try:
                raw = yf.screen(
                    q,
                    size=60,
                    sortField=sort_field,
                    sortAsc=False,
                )
                quotes.extend(_extract_quotes(raw))
            except Exception as e:
                errors.append(f"custom/{sort_field}: {e}")

    except Exception as e:
        errors.append(f"custom-query: {e}")

    # Fallbacks are intentionally broad. Some predefined screens have large-cap
    # filters, but they still give the module useful output if custom query fails.
    if not quotes:
        for preset in ("small_cap_gainers", "aggressive_small_caps", "most_shorted_stocks"):
            try:
                raw = yf.screen(preset, count=50)
                quotes.extend(_extract_quotes(raw))
            except Exception as e:
                errors.append(f"{preset}: {e}")

    # Deduplicate symbols and retain only common equity-like quotes.
    out = {}
    for x in quotes:
        if not isinstance(x, dict):
            continue
        symbol = str(x.get("symbol") or "").upper().strip()
        if not symbol or len(symbol) > 8:
            continue
        qt = str(x.get("quoteType") or x.get("typeDisp") or "EQUITY").upper()
        if qt not in ("EQUITY", "STOCK", ""):
            continue
        out[symbol] = x

    return list(out.values()), errors


def _rvol_points(rvol):
    if rvol is None:
        return 0
    if rvol >= 20:
        return 25
    if rvol >= 10:
        return 22
    if rvol >= 5:
        return 18
    if rvol >= 3:
        return 15
    if rvol >= 2:
        return 11
    if rvol >= 1.3:
        return 6
    return 0


def _explosive_item(x):
    symbol = str(x.get("symbol") or "").upper().strip()

    price = _num(
        x.get("regularMarketPrice"),
        _num(x.get("intradayprice"))
    )
    change_pct = _num(
        x.get("regularMarketChangePercent"),
        _num(x.get("percentchange"), 0.0)
    ) or 0.0
    volume = _num(
        x.get("regularMarketVolume"),
        _num(x.get("dayvolume"), 0.0)
    ) or 0.0
    avg_volume = _num(
        x.get("averageDailyVolume3Month"),
        _num(x.get("avgdailyvol3m"))
    )
    market_cap = _num(
        x.get("marketCap"),
        _num(x.get("intradaymarketcap"))
    )
    prev_close = _num(
        x.get("regularMarketPreviousClose"),
        _num(x.get("previousclose"))
    )
    open_price = _num(
        x.get("regularMarketOpen"),
        _num(x.get("open"))
    )
    day_high = _num(x.get("regularMarketDayHigh"))
    day_low = _num(x.get("regularMarketDayLow"))

    rvol = (
        volume / avg_volume
        if avg_volume and avg_volume > 0
        else None
    )
    gap_pct = (
        (open_price / prev_close - 1) * 100
        if open_price and prev_close and prev_close > 0
        else None
    )
    range_pct = (
        (day_high - day_low) / day_low * 100
        if day_high and day_low and day_low > 0 and day_high >= day_low
        else None
    )
    dollar_volume = (
        price * volume
        if price and volume
        else 0.0
    )

    score = 0.0

    # Price impulse: enough to show ignition, capped so a late parabolic move
    # does not automatically dominate the whole ranking.
    score += min(25, max(0, change_pct) * 0.85)
    score += _rvol_points(rvol)

    # Tradable attention / liquidity.
    if dollar_volume >= 50_000_000:
        score += 15
    elif dollar_volume >= 20_000_000:
        score += 12
    elif dollar_volume >= 5_000_000:
        score += 8
    elif dollar_volume >= 1_000_000:
        score += 4

    # Gap / range show that price discovery is abnormal.
    if gap_pct is not None:
        score += min(10, max(0, gap_pct) * 0.35)

    if range_pct is not None:
        if range_pct >= 40:
            score += 10
        elif range_pct >= 20:
            score += 7
        elif range_pct >= 10:
            score += 4

    # Small-cap proxy. This is NOT the same thing as verified low float.
    if market_cap is not None:
        if market_cap < 100_000_000:
            score += 10
        elif market_cap < 300_000_000:
            score += 8
        elif market_cap < 1_000_000_000:
            score += 5

    # Very thin dollar volume is easy to manipulate and hard to execute.
    if dollar_volume < 500_000:
        score -= 12

    score = round(max(0, min(100, score)), 1)

    if score >= 78:
        state = "EXTREME"
        state_label = "🚨 Extreme Momentum"
    elif score >= 62:
        state = "HOT"
        state_label = "🔥 Hot"
    elif score >= 48:
        state = "WATCH"
        state_label = "👀 Watch"
    else:
        state = "EARLY"
        state_label = "⚪ Early"

    # Separate chase/risk layer: high score means unusual, not necessarily safe.
    if change_pct >= 80 or (range_pct is not None and range_pct >= 80):
        chase = "VERY_HIGH"
        chase_label = "🔴 เสี่ยงไล่ราคาสูงมาก"
    elif change_pct >= 40 or (gap_pct is not None and gap_pct >= 25):
        chase = "HIGH"
        chase_label = "🟠 เสี่ยงไล่ราคาสูง"
    elif change_pct >= 20:
        chase = "MEDIUM"
        chase_label = "🟡 เริ่มร้อน"
    else:
        chase = "LOWER"
        chase_label = "⚪ ยังไม่ร้อนจัด"

    if change_pct < 15 and (rvol or 0) >= 3:
        phase = "IGNITION"
        phase_label = "⚡ Ignition — Volume นำราคา"
    elif change_pct < 40:
        phase = "MOMENTUM"
        phase_label = "🔥 Momentum"
    else:
        phase = "EXTENDED"
        phase_label = "🚧 Extended"

    risk_flags = []
    if price is not None and price < 1:
        risk_flags.append("หุ้นต่ำกว่า $1 / ผันผวนสูง")
    if market_cap is not None and market_cap < 100_000_000:
        risk_flags.append("Micro-cap")
    if rvol is not None and rvol >= 10:
        risk_flags.append("Volume ผิดปกติมาก")
    if range_pct is not None and range_pct >= 30:
        risk_flags.append("Intraday range กว้างมาก")
    if change_pct >= 40:
        risk_flags.append("ราคา Extended — ระวัง halt/flush")

    return {
        "ticker": symbol,
        "name": x.get("shortName") or x.get("longName") or x.get("displayName") or symbol,
        "price": round(price, 4) if price is not None else None,
        "change_pct": round(change_pct, 2),
        "volume": int(volume) if volume else 0,
        "avg_volume_3m": int(avg_volume) if avg_volume else None,
        "rvol": round(rvol, 2) if rvol is not None else None,
        "gap_pct": round(gap_pct, 2) if gap_pct is not None else None,
        "range_pct": round(range_pct, 2) if range_pct is not None else None,
        "dollar_volume": round(dollar_volume, 2),
        "market_cap": int(market_cap) if market_cap else None,
        "explosion_score": score,
        "state": state,
        "state_label": state_label,
        "phase": phase,
        "phase_label": phase_label,
        "chase_risk": chase,
        "chase_label": chase_label,
        "risk_flags": risk_flags[:4],
        "small_cap_proxy_only": True,
    }


def build_explosive_movers(force=False):
    now = time.time()

    if (
        not force
        and _EXPLOSIVE_CACHE["data"] is not None
        and now - _EXPLOSIVE_CACHE["ts"] < _EXPLOSIVE_TTL
    ):
        cached = dict(_EXPLOSIVE_CACHE["data"])
        cached["from_cache"] = True
        return cached

    quotes, errors = _screen_candidates()
    items = []

    for x in quotes:
        try:
            item = _explosive_item(x)
            # Noise filter: keep either a meaningful move or unusual volume.
            if (
                item["change_pct"] >= 2
                or (item.get("rvol") or 0) >= 1.5
            ):
                items.append(item)
        except Exception:
            continue

    items.sort(
        key=lambda z: (
            -float(z.get("explosion_score") or 0),
            -float(z.get("rvol") or 0),
            -float(z.get("change_pct") or 0),
        )
    )

    # Avoid filling the UI with already-parabolic names only. Put a few
    # IGNITION candidates near the top if they score well enough.
    ignition = [x for x in items if x.get("phase") == "IGNITION"][:4]
    leaders = items[:16]
    merged = []
    seen = set()
    for x in ignition + leaders:
        if x["ticker"] not in seen:
            merged.append(x)
            seen.add(x["ticker"])
        if len(merged) >= 16:
            break

    payload = {
        "version": "4.9",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_discovered": len(quotes),
        "total_ranked": len(items),
        "movers": merged,
        "errors": errors[-4:],
        "from_cache": False,
        "note": (
            "Explosive Score = abnormal momentum/volume score, NOT win probability "
            "and NOT a buy signal. Small-cap is only a proxy; verified float and "
            "dilution still need separate confirmation."
        ),
    }

    _EXPLOSIVE_CACHE.update({"ts": now, "data": payload})
    return payload


@app.route("/api/explosive-movers")
def explosive_movers_api():
    try:
        force = request.args.get("force") == "1"
        return jsonify({
            "ok": True,
            "data": build_explosive_movers(force=force),
        }), 200
    except Exception as e:
        return jsonify({
            "ok": False,
            "version": "4.9",
            "error": str(e),
        }), 200


_EXPLOSIVE_UI = r'''
<style>
.explosiveGrid{display:grid;gap:10px;margin-top:12px}
.explosiveCard{background:#10263c;border:1px solid #3b536b;border-radius:16px;padding:13px}
.explosiveCard.hot{border-color:#a16b28}
.explosiveCard.extreme{border-color:#9b3e3e;box-shadow:0 0 0 1px rgba(255,90,90,.08) inset}
.explosiveHead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.explosiveTicker{font-size:21px;font-weight:900}
.explosiveScore{font-size:26px;font-weight:900;text-align:right}
.explosiveMetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.explosiveMetric{background:#132c44;border-radius:11px;padding:9px}
.explosiveMetric span{display:block;color:#9eb1c6;font-size:10px}
.explosiveMetric b{display:block;font-size:15px;margin-top:2px}
.explosiveFlags{margin-top:9px;color:#cbd9e8;font-size:11px;line-height:1.55}
@media(max-width:650px){.explosiveMetrics{grid-template-columns:1fr 1fr}}
</style>

<div class="card" id="explosiveRadarCard">
  <h2>🔥 Explosive Movers Radar</h2>
  <div class="small">
    แยกจาก Top Pick ปกติ • หา RETO-like momentum จาก Price + Volume + Gap + Liquidity + Small-cap proxy<br>
    <b>Explosion Score ไม่ใช่เปอร์เซ็นต์ชนะและไม่ใช่คำสั่งซื้อ</b>
  </div>
  <button style="margin-top:12px" onclick="loadExplosiveMovers(true)">
    🔥 สแกน Explosive Movers
  </button>
  <div id="explosiveStatus" class="status info">กดสแกนเมื่ออยากหา Volume / Squeeze ผิดปกติ</div>
  <div id="explosiveGrid" class="explosiveGrid"></div>
</div>

<script>
function emNum(v,d=2){
  const n=Number(v);
  return Number.isFinite(n)?n.toFixed(d):"—";
}
function emCompact(v){
  const n=Number(v);
  if(!Number.isFinite(n))return "—";
  if(n>=1e9)return (n/1e9).toFixed(2)+"B";
  if(n>=1e6)return (n/1e6).toFixed(1)+"M";
  if(n>=1e3)return (n/1e3).toFixed(0)+"K";
  return n.toFixed(0);
}
async function loadExplosiveMovers(force){
  const st=document.getElementById("explosiveStatus");
  const grid=document.getElementById("explosiveGrid");
  if(!st||!grid)return;
  st.className="status info";
  st.textContent="กำลังค้นหา Small-cap / Volume ignition...";
  try{
    const r=await fetch(force?"/api/explosive-movers?force=1":"/api/explosive-movers",{cache:"no-store"});
    const j=await r.json();
    if(!r.ok||!j.ok)throw Error(j.error||("HTTP "+r.status));
    const d=j.data||{};
    const arr=d.movers||[];
    st.className="status "+(arr.length?"good":"warn");
    st.textContent=`V4.9 • พบ ${d.total_ranked??0} ตัว • แสดง ${arr.length} ตัว • ${d.from_cache?"Cache":"Fresh scan"}`;
    grid.innerHTML=arr.map((x,i)=>{
      const cls=x.state==="EXTREME"?"extreme":x.state==="HOT"?"hot":"";
      const flags=(x.risk_flags||[]).length?(x.risk_flags||[]).map(v=>`⚠ ${v}`).join(" • "):"ยังไม่มี Risk flag เพิ่ม";
      return `<div class="explosiveCard ${cls}">
        <div class="explosiveHead">
          <div><div class="explosiveTicker">${i+1}. ${x.ticker}</div><div class="small">${x.state_label||""} • ${x.phase_label||""}</div></div>
          <div><div class="small" style="text-align:right">Explosion Score</div><div class="explosiveScore">${x.explosion_score??"—"}</div></div>
        </div>
        <div class="explosiveMetrics">
          <div class="explosiveMetric"><span>Change</span><b>${Number(x.change_pct)>=0?"+":""}${emNum(x.change_pct)}%</b></div>
          <div class="explosiveMetric"><span>RVOL</span><b>${x.rvol==null?"—":emNum(x.rvol)+"x"}</b></div>
          <div class="explosiveMetric"><span>Volume</span><b>${emCompact(x.volume)}</b></div>
          <div class="explosiveMetric"><span>Market Cap</span><b>${emCompact(x.market_cap)}</b></div>
          <div class="explosiveMetric"><span>Gap</span><b>${x.gap_pct==null?"—":(Number(x.gap_pct)>=0?"+":"")+emNum(x.gap_pct)+"%"}</b></div>
          <div class="explosiveMetric"><span>Day Range</span><b>${x.range_pct==null?"—":emNum(x.range_pct)+"%"}</b></div>
          <div class="explosiveMetric"><span>$ Volume</span><b>${emCompact(x.dollar_volume)}</b></div>
          <div class="explosiveMetric"><span>Chase Risk</span><b>${x.chase_label||"—"}</b></div>
        </div>
        <div class="explosiveFlags">${flags}</div>
      </div>`;
    }).join("");
  }catch(e){
    st.className="status bad";
    st.textContent="Explosive Radar โหลดไม่สำเร็จ: "+e.message;
    grid.innerHTML="";
  }
}
</script>
'''


@app.after_request
def _v49_ui(response):
    try:
        if "text/html" not in (response.content_type or "").lower():
            return response

        body = response.get_data(as_text=True)

        # Insert the module before Auto Context so Top Pick and Explosive Radar
        # remain visually separate but adjacent.
        marker = "<!-- ===================================================== -->\n<!-- AUTO CONTEXT -->"
        if "id=\"explosiveRadarCard\"" not in body and marker in body:
            body = body.replace(marker, _EXPLOSIVE_UI + "\n" + marker, 1)

        replacements = {
            "AI Market Radar V4.8.2": "AI Market Radar V4.9",
            "V4.8.2 • Leading Signal + Multi-Level Reclaim": "V4.9 • Leading Signal + Explosive Movers",
            "V4.8.2 • Leading Signal + Position Engine": "V4.9 • Leading Signal + Position Engine",
            "<b>V4.8.2</b> Leading Signal + Position Engine ": "<b>V4.9</b> Leading Signal + Position Engine ",
            "<b>V4.8.2</b> Leading Signal + Opening Confirmation": "<b>V4.9</b> Leading Signal + Opening Confirmation",
        }
        for old, new in replacements.items():
            body = body.replace(old, new)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass

    return response
