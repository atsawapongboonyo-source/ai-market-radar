"""
AI Market Radar V5.1 - Multi-Radar Rotation Engine.

Presentation/runtime extension on top of V5.0 / V4.10 engine.
Existing AI scanner, Premarket Gate, Opening Confirmation, Final Decision and
Position Engine remain untouched. This layer adds cross-theme rotation only.
"""

import scanner_v494 as v494
from flask import jsonify, request

from multi_radar import build_multi_radar
from multi_radar_research import build_rotation_research
from theme_stock_leaders import build_theme_stock_leaders

app = v494.app


@app.route("/api/multi-radar")
def _v510_multi_radar_api():
    try:
        force = str(request.args.get("force") or "").lower() in {"1", "true", "yes"}
        return jsonify({"ok": True, "data": build_multi_radar(force=force)})
    except Exception as exc:
        return jsonify({"ok": False, "version": "5.1", "error": str(exc)}), 200


@app.route("/api/multi-radar-research")
def _v510_multi_radar_research_api():
    try:
        force = str(request.args.get("force") or "").lower() in {"1", "true", "yes"}
        try:
            sessions = int(request.args.get("sessions") or 220)
        except (TypeError, ValueError):
            sessions = 220
        sessions = max(60, min(220, sessions))
        return jsonify({"ok": True, "data": build_rotation_research(force=force, sessions=sessions)})
    except Exception as exc:
        return jsonify({"ok": False, "version": "5.1-research", "error": str(exc)}), 200


@app.route("/api/theme-stock-leaders")
def _v510_theme_stock_leaders_api():
    try:
        key = str(request.args.get("theme") or "").strip().lower()
        force = str(request.args.get("force") or "").lower() in {"1", "true", "yes"}
        return jsonify({"ok": True, "data": build_theme_stock_leaders(key, force=force)})
    except Exception as exc:
        return jsonify({"ok": False, "version": "5.1-stock-bridge", "error": str(exc)}), 200


_MULTI_RADAR_UI = r"""
<style id="v510MultiRadarStyle">
.v510Card{background:#0b2135;border-color:#315a7e}
.v510Head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.v510Head h2{margin:0}.v510Badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#173d5e;border:1px solid #39749f;color:#c9e4f8}
.v510Grid{display:grid;gap:8px;margin-top:12px}
.v510Row{display:grid;grid-template-columns:30px minmax(0,1fr) 60px;gap:9px;align-items:center;background:#10263c;border:1px solid #24425f;border-radius:13px;padding:10px;cursor:pointer;transition:.15s ease}.v510Row:active{transform:scale(.99);background:#153a5b}
.v510Row.lead{border-color:#28724b;background:#103421}.v510Rank{font-size:17px;font-weight:900;color:#9eb1c6}
.v510Name{font-size:14px;font-weight:900}.v510Meta{font-size:10px;color:#91a9c1;margin-top:3px;line-height:1.35}
.v510Score{text-align:right;font-size:19px;font-weight:900}.v510Up{color:#bfe9cf}.v510Down{color:#f0b6b6}
.v510StockPanel{display:none;margin-top:12px;padding:11px;border-radius:13px;background:#0d2840;border:1px solid #39749f}.v510StockPanel.show{display:block}.v510StockGrid{display:grid;gap:7px;margin-top:8px}.v510StockRow{display:grid;grid-template-columns:28px minmax(0,1fr) 58px;gap:8px;align-items:center;background:#10263c;border:1px solid #24425f;border-radius:11px;padding:9px}.v510StockTicker{font-size:16px;font-weight:900}.v510StockMeta{font-size:10px;color:#91a9c1;line-height:1.4}.v510History{margin-top:12px;padding:11px;border-radius:13px;background:#10263c;border:1px solid #24425f}
.v510HistoryLine{font-size:11px;color:#b8c9d8;line-height:1.55}.v510Actions{display:flex;gap:8px;margin-top:12px}
.v510Actions button{margin:0;flex:1}.v510Research{display:none;margin-top:10px;padding:11px;border-radius:13px;background:#0f2a42;border:1px solid #315a7e}.v510Research.show{display:block}.v510ResearchGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v510ResearchBox{background:#10263c;border:1px solid #24425f;border-radius:12px;padding:10px}.v510ResearchBox span{display:block;font-size:10px;color:#91a9c1}.v510ResearchBox b{display:block;margin-top:4px;font-size:16px}.v510Note{margin-top:9px;font-size:10px;color:#7fa3c2;line-height:1.45}
@media(max-width:420px){.v510Row{grid-template-columns:26px minmax(0,1fr) 52px}.v510Name{font-size:13px}}
</style>
<script id="v510MultiRadar">
(function(){
  function esc(v){return String(v==null?'—':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function signed(v){var n=Number(v);return Number.isFinite(n)?(n>0?'+':'')+n.toFixed(1):'—'}
  function stateIcon(s){if(s==='LEADING')return '🟢';if(s==='EARLY_ROTATION')return '🟣';if(s==='ACCELERATING')return '🔵';if(s==='RECOVERING')return '⚪';if(s==='COOLING')return '🟠';if(s==='LAGGING')return '🔴';return '🟡'}
  function ensure(){
    if(document.getElementById('v510MultiRadarCard'))return;
    var anchor=document.getElementById('v410ThemeCard')||Array.from(document.querySelectorAll('.card')).find(function(x){return (x.textContent||'').includes('Theme Rotation')});
    var card=document.createElement('section');card.id='v510MultiRadarCard';card.className='card v510Card';
    card.innerHTML='<div class="v510Head"><div><h2>🛰 Multi-Radar Rotation</h2><div class="small" style="margin-top:5px">AI → Space → Quantum → Nuclear/SMR → Robotics → Defense/Drone → Cybersecurity</div></div><span class="v510Badge">V5.1</span></div>'+
      '<div id="v510Status" class="status info" style="margin-top:12px">กำลังโหลด Rotation Engine...</div>'+
      '<div id="v510Grid" class="v510Grid"></div>'+
      '<div id="v510StockPanel" class="v510StockPanel"><div class="small">แตะ Theme เพื่อดู Stock Leaders</div></div>'+
      '<div id="v510History" class="v510History"><div class="small">Rotation history จะขึ้นหลังโหลดข้อมูล</div></div>'+
      '<div class="v510Actions"><button onclick="window.v510LoadMultiRadar(true)">↻ Refresh Multi-Radar</button><button class="alt" onclick="window.v510LoadResearch()">Research 1Y</button></div>'+
      '<div id="v510Research" class="v510Research"><div class="small">กด Research 1Y เพื่อดู historical ranking test</div></div>'+
      '<div class="v510Note">คะแนนใช้ relative momentum + member breadth + EMA20 participation + volume confirmation เพื่อจัดลำดับกลุ่ม ไม่ใช่สัญญาณซื้อขายโดยตรง</div>';
    if(anchor)anchor.parentNode.insertBefore(card,anchor);else document.querySelector('.w')?.appendChild(card);
  }
  function render(x){
    ensure();
    var st=document.getElementById('v510Status'),grid=document.getElementById('v510Grid'),hist=document.getElementById('v510History');
    var themes=x.themes||[],leader=x.leader||null;
    if(st){st.className='status good';st.innerHTML='<b>Multi-Radar พร้อม</b>'+(leader?' • กลุ่มนำ: '+esc(leader.label)+' • Score '+esc(leader.score):'')}
    if(grid)grid.innerHTML=themes.map(function(t){
      var ac=Number(t.acceleration||0),cls=t.rank===1?' lead':'',acls=ac>0?'v510Up':ac<0?'v510Down':'';
      return '<div class="v510Row'+cls+'" role="button" tabindex="0" onclick="window.v510LoadThemeStocks(\''+esc(t.key)+'\')"><div class="v510Rank">'+esc(t.rank)+'</div><div><div class="v510Name">'+stateIcon(t.state)+' '+esc(t.label)+'</div>'+
        '<div class="v510Meta">'+esc(t.state_label)+' • '+esc(t.proxy)+' • 5D vs '+esc(x.benchmark)+' '+signed(t.proxy_rel_5d_pct)+'% • 20D '+signed(t.proxy_rel_20d_pct)+'%<br>'+
        'Breadth '+esc(t.breadth_5d_pct)+'% • EMA20 '+esc(t.above_ema20_pct)+'% • Confirm '+esc(t.rotation_confirmation_count)+'/'+esc(t.rotation_confirmation_total)+' '+esc(t.rotation_confidence)+'<br>'+
        '1D <span class="'+acls+'">'+signed(t.score_change_1d)+'</span> • 5D '+signed(t.score_change_5d)+' • Rank5 '+signed(t.rank_change_5d)+'</div></div>'+
        '<div class="v510Score">'+esc(t.score)+'</div></div>'
    }).join('');
    var h=(x.history||[]).slice(-5).reverse();
    if(hist){
      var tr=x.transition||{},watch=tr.watch_first||[],recovery=tr.recovery_watch||[];
      var watchHtml=watch.length?'<div class="small" style="margin:8px 0 4px">TRANSITION WATCH</div>'+watch.map(function(t){
        return '<div class="v510HistoryLine">'+stateIcon(t.state)+' <b>'+esc(t.label)+'</b> • '+esc(t.state_label)+' • Confirm '+esc(t.rotation_confirmation_count)+'/'+esc(t.rotation_confirmation_total)+' • 5D '+signed(t.score_change_5d)+' • Rank5 '+signed(t.rank_change_5d)+'</div>'
      }).join(''):'';
      var recoveryHtml=recovery.length?'<div class="small" style="margin:8px 0 4px">RECOVERY WATCH • ยังไม่ยืนยัน</div>'+recovery.map(function(t){
        return '<div class="v510HistoryLine">'+stateIcon(t.state)+' <b>'+esc(t.label)+'</b> • Confirm '+esc(t.rotation_confirmation_count)+'/'+esc(t.rotation_confirmation_total)+' • รอ breadth / EMA20 / relative strength</div>'
      }).join(''):'';
      var rs=x.rotation_summary||{},hand=rs.last_handoff||null;
      var summaryHtml='<div class="small" style="margin-bottom:5px">ROTATION STRUCTURE</div>'+
        '<div class="v510HistoryLine">Leader streak <b>'+esc(rs.leader_streak_sessions||0)+'</b> sessions • Handoffs '+esc(rs.leader_changes||0)+'</div>'+
        (hand?'<div class="v510HistoryLine">Last handoff <b>'+esc(hand.date)+'</b> • '+esc(hand.from_label)+' → '+esc(hand.to_label)+'</div>':'');
      hist.innerHTML=summaryHtml+'<div class="small" style="margin:8px 0 4px">RECENT ROTATION LEADERS</div>'+h.map(function(d){
        return '<div class="v510HistoryLine"><b>'+esc(d.date)+'</b> • '+esc(d.leader_label)+' • '+esc(d.leader_score)+'</div>'
      }).join('')+watchHtml+recoveryHtml;
    }
    var command=document.getElementById('v500Leader');
    if(command&&leader)command.textContent=leader.label+' • '+leader.score;
    window.v510LastMultiRadar=x;
  }
  async function load(force){
    ensure();var st=document.getElementById('v510Status');
    if(st){st.className='status info';st.textContent='กำลังคำนวณ Multi-Radar Rotation...'}
    try{
      var r=await fetch('/api/multi-radar'+(force?'?force=1':''),{cache:'no-store'}),j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));render(j.data||{});
    }catch(e){if(st){st.className='status bad';st.textContent='Multi-Radar ไม่สำเร็จ: '+e.message}}
  }
  function renderThemeStocks(x){
    var el=document.getElementById('v510StockPanel');if(!el)return;
    var rows=x.top3||[];
    el.classList.add('show');
    el.innerHTML='<div class="small">THEME → STOCK LEADER • '+esc(x.theme_label)+' • '+esc(x.proxy)+'</div>'+
      '<div class="v510StockGrid">'+rows.map(function(s){
        return '<div class="v510StockRow"><div class="v510Rank">'+esc(s.rank)+'</div><div>'+
          '<div class="v510StockTicker">'+esc(s.ticker)+' <span class="small">'+esc(s.state_label)+'</span></div>'+
          '<div class="v510StockMeta">Score '+esc(s.leader_score)+' • Confirm '+esc(s.confirmation_count)+'/'+esc(s.confirmation_total)+
          ' • 5D vs Theme '+signed(s.relative_proxy_5d_pct)+'% • 20D '+signed(s.relative_proxy_20d_pct)+'%<br>'+
          '1D '+signed(s.return_1d_pct)+'% • Vol '+esc(s.volume_ratio)+'x • EMA20 '+(s.above_ema20?'เหนือ':'ต่ำกว่า')+'</div></div>'+
          '<div class="v510Score">'+esc(s.leader_score)+'</div></div>'
      }).join('')+'</div>'+
      '<div class="v510Note">จัดอันดับภายใน Theme เท่านั้น • ยังต้องผ่าน Scanner / Premarket / Opening เดิมก่อนตัดสินใจ</div>';
    try{el.scrollIntoView({behavior:'smooth',block:'nearest'})}catch(e){}
  }
  async function loadThemeStocks(key){
    ensure();var el=document.getElementById('v510StockPanel');if(!el)return;
    el.classList.add('show');el.innerHTML='<div class="small">กำลังคำนวณ Stock Leaders...</div>';
    try{
      var r=await fetch('/api/theme-stock-leaders?theme='+encodeURIComponent(key),{cache:'no-store'}),j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));renderThemeStocks(j.data||{});
    }catch(e){el.innerHTML='<div class="status bad">Stock Leader Bridge ไม่สำเร็จ: '+esc(e.message)+'</div>'}
  }
  window.v510LoadThemeStocks=loadThemeStocks;
  function researchBox(label,stat,suffix){
    stat=stat||{};
    return '<div class="v510ResearchBox"><span>'+esc(label)+'</span><b>'+signed(stat.avg)+(suffix||'%')+'</b><div class="small">Median '+signed(stat.median)+'% • Positive '+esc(stat.positive_pct)+'% • n='+esc(stat.n)+'</div></div>';
  }
  function renderResearch(x){
    var el=document.getElementById('v510Research');if(!el)return;
    var c=x.cross_sectional||{},d5=c['5']||{},d3=c['3']||{};
    el.classList.add('show');
    el.innerHTML='<div class="small" style="margin-bottom:8px">RESEARCH • CROSS-SECTIONAL RANKING • '+esc(x.sessions_requested)+' sessions</div>'+
      '<div class="v510ResearchGrid">'+
        researchBox('5D Leader vs QQQ',d5.top1_vs_qqq)+
        researchBox('5D #1 − Last',d5.top1_minus_bottom1)+
        researchBox('5D Top2 − Bottom2',d5.top2_minus_bottom2)+
        '<div class="v510ResearchBox"><span>5D Leader in Top Half</span><b>'+esc(d5.leader_top_half_pct)+'%</b><div class="small">Non-overlapping ranking windows</div></div>'+
      '</div>'+
      '<div class="v510HistoryLine" style="margin-top:8px">3D #1 − Last '+signed((d3.top1_minus_bottom1||{}).avg)+'% • 5D sample n='+esc((d5.top1_minus_bottom1||{}).n)+'</div>'+
      '<div class="v510Note">Research only • current-universe / survivorship bias possible • ไม่ใช่ Buy Signal และไม่ถูกใช้เปลี่ยน live decision engine</div>';
  }
  async function loadResearch(){
    ensure();var el=document.getElementById('v510Research');if(!el)return;
    el.classList.add('show');el.innerHTML='<div class="small">กำลังคำนวณ Research 1Y...</div>';
    try{
      var r=await fetch('/api/multi-radar-research?sessions=220',{cache:'no-store'}),j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));renderResearch(j.data||{});
    }catch(e){el.innerHTML='<div class="status bad">Research ไม่สำเร็จ: '+esc(e.message)+'</div>'}
  }
  window.v510LoadMultiRadar=load;
  window.v510LoadResearch=loadResearch;
  function hookScan(){
    if(window.__v510ScanHooked)return;
    var original=window.scan;if(typeof original!=='function')return;
    window.__v510ScanHooked=true;
    window.scan=async function(force){
      var out=await original(force);
      try{await load(false)}catch(e){}
      return out;
    };
  }
  function boot(){ensure();hookScan();load(false)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(function(){ensure();hookScan()},800);
})();
</script>
"""


@app.after_request
def _v510_inject_multi_radar(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v510MultiRadar" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _MULTI_RADAR_UI + "\n" + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response
