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
<style id="v500ShellStyle">
:root{--v5nav-h:72px}
body{padding-bottom:calc(var(--v5nav-h) + env(safe-area-inset-bottom))}
.v500BottomNav{
  position:fixed;left:0;right:0;bottom:0;z-index:9999;
  height:calc(var(--v5nav-h) + env(safe-area-inset-bottom));
  padding:7px 8px calc(7px + env(safe-area-inset-bottom));
  background:rgba(6,20,35,.97);border-top:1px solid #24425f;
  display:grid;grid-template-columns:repeat(5,1fr);gap:4px;
  backdrop-filter:blur(12px)
}
.v500NavBtn{
  border:0;background:transparent!important;padding:6px 2px!important;
  min-width:0;border-radius:12px;color:#91a9c1;font-size:10px!important;
  font-weight:800!important;line-height:1.15
}
.v500NavBtn span{display:block;font-size:19px;margin-bottom:3px}
.v500NavBtn.active{color:#fff;background:#153a5b!important}
.v500TopBadge{
  display:inline-flex;align-items:center;gap:6px;margin-top:7px;
  padding:5px 9px;border-radius:20px;background:#102b43;
  border:1px solid #2f658e;color:#bcd3e8;font-size:11px;font-weight:800
}
.v500Command{background:#0b2135;border-color:#315a7e}
.v500CommandHead{display:flex;justify-content:space-between;gap:10px;align-items:center}
.v500CommandHead h2{margin:0}
.v500Live{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#103421;border:1px solid #28724b;color:#bfe9cf}
.v500SummaryGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.v500SummaryBox{background:#112b43;border:1px solid #24425f;border-radius:14px;padding:12px}
.v500SummaryBox span{display:block;font-size:11px;color:#9eb1c6}
.v500SummaryBox b{display:block;margin-top:4px;font-size:17px}
.v500Picks{display:grid;gap:8px;margin-top:12px}
.v500Pick{display:grid;grid-template-columns:34px 1fr auto;gap:9px;align-items:center;background:#10263c;border:1px solid #24425f;border-radius:13px;padding:10px;cursor:pointer;transition:.15s ease}.v500Pick:active{transform:scale(.985);background:#153a5b}.v500PickHint{font-size:10px;color:#7fa3c2;margin-top:2px}
.v500PickRank{font-size:18px;font-weight:900;color:#9eb1c6}
.v500PickTicker{font-size:18px;font-weight:900}
.v500PickScore{text-align:right;font-size:18px;font-weight:900}
.v500Next{margin-top:12px;padding:13px;border-radius:14px;background:#10263c;border:1px solid #315a7e;line-height:1.5}
.v500Next span{display:block;font-size:11px;color:#9eb1c6;margin-bottom:4px}
.v500Command button{margin-top:12px}
@media(max-width:420px){.v500SummaryGrid{grid-template-columns:1fr 1fr}.v500Pick{grid-template-columns:28px 1fr auto}}
@media(min-width:850px){.v500BottomNav{left:50%;transform:translateX(-50%);max-width:720px;border:1px solid #24425f;border-bottom:0;border-radius:18px 18px 0 0}}
</style>
<script id="v500Finalizer">
(function(){
  function byTextHeading(text){
    return Array.from(document.querySelectorAll('h2')).find(x=>(x.textContent||'').includes(text));
  }
  function cardForHeading(text){
    const h=byTextHeading(text);
    return h ? h.closest('.card,.openingCard') : null;
  }
  function targetId(el,id){if(el&&!el.id)el.id=id;return el}
  function go(id,btn){
    const el=document.getElementById(id);
    if(el)el.scrollIntoView({behavior:'smooth',block:'start'});
    document.querySelectorAll('.v500NavBtn').forEach(x=>x.classList.remove('active'));
    if(btn)btn.classList.add('active');
  }
  function apply(){
    document.title='AI Market Radar V5.0';
    const h=document.querySelector('.head .mut');
    if(h) h.textContent='V5.0 • Mobile Command Center • V4.10 Engine';

    const head=document.querySelector('.head > div:first-child');
    if(head&&!document.getElementById('v500Badge')){
      const b=document.createElement('div');
      b.id='v500Badge';b.className='v500TopBadge';
      b.textContent='V4.10 Logic Locked ✓';
      head.appendChild(b);
    }

    targetId(document.querySelector('.w > .card'),'v500Home');

    if(!document.getElementById('v500Command')){
      const home=document.getElementById('v500Home');
      if(home){
        const c=document.createElement('section');
        c.id='v500Command';c.className='card v500Command';
        c.innerHTML=
          '<div class="v500CommandHead"><h2>⚡ Command Center</h2><span class="v500Live">V5.0</span></div>'+
          '<div class="small" style="margin-top:6px">สรุปหลัง Scan: Market → Theme → Top Picks → NEXT ACTION</div>'+
          '<div class="v500SummaryGrid">'+
            '<div class="v500SummaryBox"><span>MARKET</span><b id="v500Market">รอ Scan</b></div>'+
            '<div class="v500SummaryBox"><span>LEADING THEME</span><b id="v500Leader">รอ Scan</b></div>'+
          '</div>'+
          '<div id="v500Picks" class="v500Picks"><div class="small">Top Picks จะขึ้นหลังระบบคัดเสร็จ</div></div>'+
          '<div class="v500Next"><span>NEXT ACTION</span><b id="v500Next">กด Scan Watchlist เพื่อเริ่ม</b></div>'+
          '<button class="alt" onclick="scan(false)">↻ อัปเดต Command Center</button>';
        home.insertAdjacentElement('afterend',c);
      }
    }

    targetId(cardForHeading('Candidate Ranking'),'v500Scanner');
    targetId(cardForHeading('Top Pick Engine'),'v500TopPick');
    targetId(document.getElementById('positionCard'),'v500Position');
    targetId(cardForHeading('Theme Rotation'),'v500Theme');

    document.querySelectorAll('.versionPill').forEach(p=>p.textContent='V5.0 UI');

    if(!document.getElementById('v500BottomNav')){
      const nav=document.createElement('nav');
      nav.id='v500BottomNav';nav.className='v500BottomNav';
      nav.innerHTML=
        '<button class="v500NavBtn active" data-go="v500Home"><span>⌂</span>Home</button>'+
        '<button class="v500NavBtn" data-go="v500Scanner"><span>⌕</span>Scanner</button>'+
        '<button class="v500NavBtn" data-go="v500TopPick"><span>★</span>Top Pick</button>'+
        '<button class="v500NavBtn" data-go="v500Position"><span>▣</span>Position</button>'+
        '<button class="v500NavBtn" data-go="v500Theme"><span>◈</span>Theme</button>';
      document.body.appendChild(nav);
      nav.querySelectorAll('[data-go]').forEach(btn=>btn.addEventListener('click',()=>go(btn.dataset.go,btn)));
    }
  }
  function v5txt(id,fallback){
    const e=document.getElementById(id);const t=(e&&e.textContent||'').trim();
    return t&&t!=='—'?t:fallback;
  }
  function v500OpenPick(index){
    const cards=Array.from(document.querySelectorAll('#topPicks .pickCard'));
    const card=cards[index];
    if(!card)return;
    card.click();
    const topBtn=document.querySelector('.v500NavBtn[data-go="v500TopPick"]');
    document.querySelectorAll('.v500NavBtn').forEach(x=>x.classList.remove('active'));
    if(topBtn)topBtn.classList.add('active');
    setTimeout(()=>{const confirm=document.getElementById('confirm');if(confirm)confirm.scrollIntoView({behavior:'smooth',block:'start'})},120);
  }
  window.v500OpenPick=v500OpenPick;
  function renderCommand(){
    const m=document.getElementById('v500Market');
    const l=document.getElementById('v500Leader');
    const n=document.getElementById('v500Next');
    const p=document.getElementById('v500Picks');
    if(m)m.textContent=v5txt('market','รอ Scan');
    const lead=document.querySelector('#v410ThemeGrid .v410ThemeItem.lead .v410ThemeName');
    if(l)l.textContent=lead?(lead.textContent||'').replace(/^\s*[🟢🔴🟡⚪]\s*/u,'').trim():'ยังไม่มีกลุ่มนำ';
    if(n){
      const next=document.getElementById('v410Next');
      const raw=(next&&next.textContent||'').replace(/^\s*NEXT ACTION\s*/i,'').trim();
      n.textContent=raw||'รอ Theme Rotation + Top Pick';
    }
    if(p){
      const cards=Array.from(document.querySelectorAll('#topPicks .pickCard')).slice(0,3);
      p.innerHTML=cards.length?cards.map((c,i)=>{
        const ticker=(c.querySelector('.ticker')?.textContent||'').replace(/\s+/g,' ').trim();
        const score=(c.querySelector('.pickScore')?.textContent||'—').trim();
        return '<div class="v500Pick" role="button" tabindex="0" onclick="v500OpenPick('+i+')" aria-label="เปิด Final Confirmation อันดับ '+(i+1)+'"><div class="v500PickRank">'+(i+1)+'</div><div><div class="v500PickTicker">'+ticker+'</div><div class="small">Watch Score • ใช้เพื่อจัดลำดับเฝ้าดู</div><div class="v500PickHint">แตะเพื่อเปิด Final Confirmation →</div></div><div class="v500PickScore">'+score+'</div></div>';
      }).join(''):'<div class="small">Top Picks จะขึ้นหลังระบบคัดเสร็จ</div>';
    }
  }
  function hookCommand(){
    if(window.__v500CommandHooked)return;
    window.__v500CommandHooked=true;
    const originalScan=window.scan;
    if(typeof originalScan==='function'){
      window.scan=async function(force){
        const out=await originalScan(force);
        try{if(typeof window.v410LoadThemeRotation==='function')await window.v410LoadThemeRotation()}catch(e){}
        renderCommand();setTimeout(renderCommand,500);setTimeout(renderCommand,1800);
        return out;
      };
    }
    const tp=document.getElementById('topPicks');
    const th=document.getElementById('v410ThemeGrid');
    const mk=document.getElementById('market');
    const obs=new MutationObserver(()=>renderCommand());
    [tp,th,mk].filter(Boolean).forEach(x=>obs.observe(x,{childList:true,subtree:true,characterData:true}));
    renderCommand();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{apply();hookCommand()},{once:true});else{apply();hookCommand()}
  setTimeout(()=>{apply();hookCommand();renderCommand()},250);
  setTimeout(()=>{apply();hookCommand();renderCommand()},1000);
})();
</script>
"""


@app.after_request
def _v494_visible_version(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            # Flask after_request hooks run in reverse registration order.
            # Prepend V5 so it executes AFTER every legacy V4.x inline/finalizer
            # script, preventing old version labels from overwriting V5.
            # scanner.html contains an old literal "</body>" inside a legacy
            # HTML comment. Always inject before the LAST closing body tag so
            # the V5 shell executes outside that comment.
            if "v500Finalizer" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _FINAL_UI + "\n" + body[pos:]
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response



# V5.0 hard route wrapper: inject shell at the view response level, after all
# legacy module loading. This avoids Flask after_request ordering entirely.
def _v500_inject_response(rv):
    try:
        response = app.make_response(rv)
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v500Finalizer" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _FINAL_UI + "\n" + body[pos:]
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response
    except Exception:
        return rv


_v500_home = app.view_functions.get("home")
if _v500_home:
    def _v500_home_view(*args, **kwargs):
        return _v500_inject_response(_v500_home(*args, **kwargs))
    app.view_functions["home"] = _v500_home_view

_v500_scanner = app.view_functions.get("scanner_page")
if _v500_scanner:
    def _v500_scanner_view(*args, **kwargs):
        return _v500_inject_response(_v500_scanner(*args, **kwargs))
    app.view_functions["scanner_page"] = _v500_scanner_view

# V5 route ownership fix: legacy /scanner calls scanner_home() directly,
# so wrapping only app.view_functions["scanner_page"] does not cover the
# rendered page. Patch legacy scanner_home itself while leaving all scanner
# and decision-engine logic untouched.
_v500_legacy_scanner_home = base.scanner_home

def _v500_legacy_scanner_home_view(*args, **kwargs):
    return _v500_inject_response(_v500_legacy_scanner_home(*args, **kwargs))

base.scanner_home = _v500_legacy_scanner_home_view
app.view_functions["home"] = _v500_legacy_scanner_home_view

# Rebind /scanner explicitly because Flask registered the original function
# object before this V5 layer was loaded.
def _v500_scanner_page_view(*args, **kwargs):
    return _v500_legacy_scanner_home_view()

app.view_functions["scanner_page"] = _v500_scanner_page_view

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
