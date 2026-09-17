"""
AI MARKET RADAR V4.9.3

Explosive Movers quality calibration on top of V4.9.2.

Fixes observed from live output:
- remove warrants / preferred-like special issues from the common-stock radar
- do not treat missing market cap as a clean signal
- tighten IGNITION so a nearly parabolic intraday range cannot be called early
- prioritize clean ignition candidates rather than all ignition candidates
- expose signal/data quality metadata for the UI
"""

import scanner_v492 as v492
import scanner_v49 as v49

app = v492.app

_prev_explosive_item = v49._explosive_item
_prev_screen_candidates = v49._screen_candidates


def _text(x, key):
    try:
        return str(x.get(key) or "").strip()
    except Exception:
        return ""


def _special_issue_reason(x):
    symbol = _text(x, "symbol").upper()
    name = " ".join([
        _text(x, "shortName"),
        _text(x, "longName"),
        _text(x, "displayName"),
        _text(x, "typeDisp"),
    ]).lower()

    if any(k in name for k in ("warrant", "warrants", "right", "rights")):
        return "warrant/right"

    # Nasdaq fifth-letter conventions commonly use W for warrants and P for
    # preferred issues. Restrict this heuristic to longer symbols to avoid
    # excluding ordinary 3-4 letter companies accidentally.
    if len(symbol) >= 5 and (
        symbol.endswith("WW")
        or symbol.endswith("WS")
        or symbol.endswith("WT")
        or symbol.endswith("W")
    ):
        return "warrant-like symbol"

    if "preferred" in name or (len(symbol) >= 5 and symbol.endswith("P")):
        return "preferred-like issue"

    return None


def _screen_candidates_v493():
    quotes, errors = _prev_screen_candidates()
    clean = []
    removed = 0

    for x in quotes:
        reason = _special_issue_reason(x)
        if reason:
            removed += 1
            continue
        clean.append(x)

    if removed:
        errors = list(errors or []) + [
            f"quality-filter: removed {removed} warrant/preferred-like issues"
        ]

    return clean, errors


def _explosive_item_v493(x):
    item = dict(_prev_explosive_item(x) or {})

    price = item.get("price")
    change = float(item.get("change_pct") or 0)
    rvol = item.get("rvol")
    gap = item.get("gap_pct")
    day_range = item.get("range_pct")
    dollar_volume = float(item.get("dollar_volume") or 0)
    market_cap = item.get("market_cap")

    data_flags = []

    if market_cap in (None, 0):
        data_flags.append("Market Cap ไม่พร้อม")

    if price is None or price <= 0:
        data_flags.append("ราคาไม่พร้อม")

    if gap is not None and abs(float(gap)) > 200:
        data_flags.append("Gap ผิดปกติ > 200% — ต้องตรวจ corporate action/data")

    # Clean ignition should look early, liquid enough, and not already have a
    # huge intraday expansion. The goal is to find volume leading price.
    ignition_clean = (
        2 <= change <= 15
        and rvol is not None
        and float(rvol) >= 3
        and dollar_volume >= 1_000_000
        and (day_range is None or float(day_range) <= 25)
        and (gap is None or -5 <= float(gap) <= 12)
        and not data_flags
    )

    if ignition_clean:
        item["phase"] = "IGNITION"
        item["phase_label"] = "⚡ Clean Ignition — Volume นำราคา"
        item["signal_quality"] = "CLEAN"
        item["signal_quality_label"] = "🟢 Clean setup"

    elif data_flags:
        item["phase"] = "DATA_CHECK"
        item["phase_label"] = "🧪 Data Check"
        item["signal_quality"] = "DATA_CHECK"
        item["signal_quality_label"] = "⚪ ต้องตรวจข้อมูล"

    elif change >= 40 or (day_range is not None and float(day_range) >= 50):
        item["phase"] = "EXTENDED"
        item["phase_label"] = "🚧 Extended / High volatility"
        item["signal_quality"] = "SPECULATIVE"
        item["signal_quality_label"] = "🔴 Speculative"

    else:
        item["phase"] = "MOMENTUM"
        item["phase_label"] = "🔥 Momentum"
        item["signal_quality"] = "MOMENTUM"
        item["signal_quality_label"] = "🟡 Momentum"

    item["data_flags"] = data_flags
    item["clean_ignition"] = ignition_clean

    # Extra penalty for unreliable metadata so it cannot outrank a clean setup.
    if data_flags:
        item["explosion_score"] = round(
            max(0, float(item.get("explosion_score") or 0) - 18),
            1,
        )

    return item


def build_explosive_movers_v493(force=False):
    # Rebuild using the same free discovery source, but with V4.9.3 filters.
    quotes, errors = _screen_candidates_v493()
    items = []

    for x in quotes:
        try:
            item = _explosive_item_v493(x)
            if (
                item["change_pct"] >= 2
                or (item.get("rvol") or 0) >= 1.5
            ):
                items.append(item)
        except Exception:
            continue

    items.sort(
        key=lambda z: (
            0 if z.get("clean_ignition") else 1,
            1 if z.get("signal_quality") == "DATA_CHECK" else 0,
            -float(z.get("explosion_score") or 0),
            -float(z.get("rvol") or 0),
            -float(z.get("change_pct") or 0),
        )
    )

    clean_ignition = [x for x in items if x.get("clean_ignition")][:5]
    leaders = [
        x for x in items
        if x.get("signal_quality") != "DATA_CHECK"
    ][:16]
    data_checks = [
        x for x in items
        if x.get("signal_quality") == "DATA_CHECK"
    ][:2]

    merged = []
    seen = set()
    for x in clean_ignition + leaders + data_checks:
        if x["ticker"] not in seen:
            merged.append(x)
            seen.add(x["ticker"])
        if len(merged) >= 16:
            break

    import time
    payload = {
        "version": "4.9.3",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_discovered": len(quotes),
        "total_ranked": len(items),
        "clean_ignition_count": len([x for x in items if x.get("clean_ignition")]),
        "movers": merged,
        "errors": list(errors or [])[-5:],
        "from_cache": False,
        "note": (
            "V4.9.3 prioritizes clean common-stock ignition. Warrants/preferred-like "
            "issues are filtered; missing/abnormal metadata is downgraded to Data Check. "
            "Explosion Score is NOT win probability and NOT a buy signal."
        ),
    }
    return payload


# Patch the module where the already-registered API route resolves its globals.
v49._screen_candidates = _screen_candidates_v493
v49._explosive_item = _explosive_item_v493
v49.build_explosive_movers = build_explosive_movers_v493


_FINAL_UI = r'''
<script id="v493Finalizer">
(function(){
  function apply(){
    document.title='AI Market Radar V4.9.3';
    const h=document.querySelector('.head .mut');
    if(h) h.textContent='V4.9.3 • Leading Signal + Explosive Movers';

    const card=document.getElementById('explosiveRadarCard');
    if(card){
      const small=card.querySelector('.small');
      if(small) small.innerHTML='แยกจาก Top Pick ปกติ • V4.9.3 กรอง warrant/preferred + Data anomaly และให้ Clean Ignition มาก่อน<br><b>Explosion Score ไม่ใช่เปอร์เซ็นต์ชนะและไม่ใช่คำสั่งซื้อ</b>';
    }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',apply,{once:true});
  else apply();
  setTimeout(apply,250);
  setTimeout(apply,1000);
})();
</script>
'''


@app.after_request
def _v493_visible_version(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v493Finalizer" not in body:
                body = body.replace("</body>", _FINAL_UI + "\n</body>", 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response
