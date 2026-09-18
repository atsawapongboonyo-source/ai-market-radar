"""
AI MARKET RADAR V4.9.4

Live-test safety patch for the V4.7.2 issues discovered in Opening Confirmation:
1) every completed Opening response carries Open/High/Low/Mid so Position Engine
   can persist the same opening state into Reclaim Roadmap;
2) negative high-impact catalyst blocks NEW entry but does not by itself mark
   the price structure INVALIDATED;
3) stale cached scanner data is treated as DATA_STALE/WATCH, not structural
   invalidation.

The existing V4.9.3 Leading Signal / Explosive Movers stack remains intact.
"""

import scanner_v493 as v493
import legacy_scanner as base
from flask import jsonify

app = v493.app

_prev_opening_confirmation = base._opening_confirmation


def _opening_payload(p):
    """Build canonical opening fields directly from validated request inputs."""
    try:
        op = float(p.get("open_price"))
        hi = float(p.get("opening_high"))
        lo = float(p.get("opening_low"))
        px = float(p.get("price"))
        if min(op, hi, lo, px) <= 0 or lo > hi:
            return None
        mid = (hi + lo) / 2.0
        return {
            "open": round(op, 2),
            "high": round(hi, 2),
            "low": round(lo, 2),
            "mid": round(mid, 2),
            "change_from_open_pct": round((px - op) / op * 100.0, 2),
            "range_pct": round((hi - lo) / op * 100.0, 2),
        }
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _opening_confirmation_v494(p):
    result = dict(_prev_opening_confirmation(p) or {})
    opening = _opening_payload(p)

    # The legacy engine has several intentional early exits. Those exits used
    # to omit "opening", which made the frontend display dashes and prevented
    # V4.7.1 Position/Reclaim from receiving Open and Mid.
    if opening is not None:
        existing = result.get("opening")
        if isinstance(existing, dict):
            merged = dict(opening)
            merged.update({k: v for k, v in existing.items() if v is not None})
            result["opening"] = merged
        else:
            result["opening"] = opening

    negative_high = bool(p.get("negative_high_impact"))
    confidence = str(p.get("data_confidence") or "FRESH").upper()

    # News risk is an entry guard, not proof that the price structure broke.
    if negative_high and result.get("reason") == "มีข่าวลบ Impact สูง":
        result.update({
            "status": "BLOCK",
            "state": "WATCH",
            "score": 20,
            "label": "🟠 RISK REVIEW • งดเข้าใหม่",
            "reason": "มีข่าวลบ Impact สูง • Block New Entry แต่โครงสร้างราคายังไม่ถือว่า Invalidated",
            "checks": [
                "🟠 Catalyst Risk สูง — งดเปิด/เพิ่ม Position ใหม่",
                "⚪ INVALIDATED จะใช้เมื่อโครงสร้างราคาเสีย เช่น ราคาหลุด Stop",
            ],
            "next_step": "ติดตามข่าวและโครงสร้างราคา • ประเมินใหม่เมื่อ Catalyst Risk คลี่คลาย",
        })

    # Cached data also should not masquerade as structural invalidation.
    if confidence == "CACHED" and result.get("reason") == "ข้อมูลหุ้นยังเป็น Cache":
        result.update({
            "status": "BLOCK",
            "state": "WATCH",
            "score": 0,
            "label": "⚪ DATA STALE • รอ Refresh",
            "reason": "ข้อมูล Scanner เป็น Cache • ยังไม่ใช้ยืนยัน Opening",
            "checks": ["⚪ Refresh Scanner ให้เป็น Fresh/Recovered ก่อน"],
            "next_step": "Refresh ข้อมูล แล้วตรวจ Opening Confirmation ใหม่",
        })

    result["version"] = "4.9.4"
    return result


# Existing Flask route resolves this name from legacy_scanner globals.
base._opening_confirmation = _opening_confirmation_v494


_FINAL_UI = r"""
<script id="v494Finalizer">
(function(){
  function apply(){
    document.title='AI Market Radar V4.9.4';
    const h=document.querySelector('.head .mut');
    if(h) h.textContent='V4.9.4 • Opening State + Catalyst Safety Fix';

    const openingCard=document.querySelector('.openingCard');
    if(openingCard){
      const pill=openingCard.querySelector('.versionPill');
      if(pill) pill.textContent='V4.9.4';
    }

    const positionCard=document.getElementById('positionCard');
    if(positionCard){
      const pill=positionCard.querySelector('.versionPill');
      if(pill) pill.textContent='V4.9.4';
    }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',apply,{once:true});
  else apply();
  setTimeout(apply,250);
  setTimeout(apply,1000);
})();
</script>
"""


@app.after_request
def _v494_visible_version(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v494Finalizer" not in body:
                body = body.replace("</body>", _FINAL_UI + "\n</body>", 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response


# V4.10 Theme Rotation / Market Context
def _v410_theme_rotation():
    # Scanner data and Auto Context are owned by legacy_scanner.
    scan = base.scan_watchlist(force=False)
    ctx = dict(scan.get("auto_context") or {})
    groups = dict(ctx.get("groups") or {})
    labels = {
        "network": "Optical / Networking",
        "memory": "Memory / Storage",
        "chip": "Chips / Equipment",
        "datacenter": "Datacenter / Compute",
        "power": "Power / Energy",
        "cloud": "Cloud / Hyperscalers",
        "software": "AI Software",
    }
    themes = []
    market = float(ctx.get("market_score") or 0)
    # legacy Auto Context does not expose breadth_pct/regime yet.
    # Convert its normalized market_score (-1..+1) to a display breadth
    # where 50% = neutral, while keeping the original market signal intact.
    breadth_pct = round(max(0.0, min(100.0, 50.0 + market * 50.0)), 1)
    market_state = str(ctx.get("market") or "unknown").lower()
    regime = (
        "risk_on" if market_state == "bull"
        else "risk_off" if market_state == "bear"
        else "mixed"
    )
    regime_label = (
        "Risk-On" if regime == "risk_on"
        else "Risk-Off" if regime == "risk_off"
        else "Mixed"
    )
    for key, label in labels.items():
        g = dict(groups.get(key) or {})
        count = int(g.get("count") or 0)
        strength = float(g.get("strength") or 0)
        confidence = "HIGH" if count >= 4 else "MEDIUM" if count >= 2 else "LOW"
        effective = g.get("effective_relative_strength")
        if effective is None:
            weight = 1.0 if count >= 4 else .65 if count >= 2 else 0.0
            effective = (strength - market) * weight
        score = round(max(-100, min(100, float(effective) * 100)), 1)
        if confidence == "LOW":
            state, state_label = "LOW_SAMPLE", "Sample low"
        elif score >= 12:
            state, state_label = "LEADING", "Leading"
        elif score <= -12:
            state, state_label = "LAGGING", "Lagging"
        else:
            state, state_label = "NEUTRAL", "Neutral"
        themes.append({
            "key": key, "label": label, "state": state,
            "state_label": state_label, "theme_score": score,
            "member_count": count, "confidence": confidence,
        })
    themes.sort(key=lambda x: (1 if x["confidence"] == "LOW" else 0, -x["theme_score"]))
    valid = [x for x in themes if x["confidence"] != "LOW"]
    leader = valid[0] if valid else None
    if leader and leader["theme_score"] >= 12:
        next_action = "Watch " + leader["label"] + " first; individual stocks still require Premarket + Opening confirmation."
    elif regime == "risk_off":
        next_action = "Risk-Off: avoid chasing and wait for stronger confirmation."
    else:
        next_action = "No clear leading theme; use Top Pick + Opening Confirmation."
    return {
        "version": "4.10",
        "market_regime": regime,
        "market_regime_label": regime_label,
        "market_breadth_pct": breadth_pct,
        "themes": themes, "leader": leader, "next_action": next_action,
        "note": "Theme Score is relative AI-watchlist breadth, not fund flow, win probability, or a buy signal.",
    }


@app.route("/api/theme-rotation")
def _v410_theme_rotation_api():
    try:
        return jsonify({"ok": True, "data": _v410_theme_rotation()})
    except Exception as e:
        return jsonify({"ok": False, "version": "4.10", "error": str(e)}), 200
