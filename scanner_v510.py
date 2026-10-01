"""
AI Market Radar V5.1 - Multi-Radar Rotation Engine.

Presentation/runtime extension on top of V5.0 / V4.10 engine.
Existing AI scanner, Premarket Gate, Opening Confirmation, Final Decision and
Position Engine remain untouched. This layer adds cross-theme rotation only.
"""

import scanner_v494 as v494
from flask import jsonify, request

from multi_radar import build_multi_radar

app = v494.app


@app.route("/api/multi-radar")
def _v510_multi_radar_api():
    try:
        force = str(request.args.get("force") or "").lower() in {"1", "true", "yes"}
        return jsonify({"ok": True, "data": build_multi_radar(force=force)})
    except Exception as exc:
        return jsonify({"ok": False, "version": "5.1", "error": str(exc)}), 200


_MULTI_RADAR_UI = r"""
<style id="v510MultiRadarStyle">
.v510Card{background:#0b2135;border-color:#315a7e}
.v510Head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.v510Head h2{margin:0}.v510Badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#173d5e;border:1px solid #39749f;color:#c9e4f8}
.v510Grid{display:grid;gap:8px;margin-top:12px}
.v510Row{display:grid;grid-template-columns:30px minmax(0,1fr) 60px;gap:9px;align-items:center;background:#10263c;border:1px solid #24425f;border-radius:13px;padding:10px}
.v510Row.lead{border-color:#28724b;background:#103421}.v510Rank{font-size:17px;font-weight:900;color:#9eb1c6}
.v510Name{font-size:14px;font-weight:900}.v510Meta{font-size:10px;color:#91a9c1;margin-top:3px;line-height:1.35}
.v510Score{text-align:right;font-size:19px;font-weight:900}.v510Up{color:#bfe9cf}.v510Down{color:#f0b6b6}
.v510History{margin-top:12px;padding:11px;border-radius:13px;background:#10263c;border:1px solid #24425f}
.v510HistoryLine{font-size:11px;color:#b8c9d8;line-height:1.55}.v510Actions{display:flex;gap:8px;margin-top:12px}
.v510Actions button{margin:0;flex:1}.v510Note{margin-top:9px;font-size:10px;color:#7fa3c2;line-height:1.45}
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
      '<div id="v510History" class="v510History"><div class="small">Rotation history จะขึ้นหลังโหลดข้อมูล</div></div>'+
      '<div class="v510Actions"><button onclick="window.v510LoadMultiRadar(true)">↻ Refresh Multi-Radar</button></div>'+
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
      return '<div class="v510Row'+cls+'"><div class="v510Rank">'+esc(t.rank)+'</div><div><div class="v510Name">'+stateIcon(t.state)+' '+esc(t.label)+'</div>'+
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
  window.v510LoadMultiRadar=load;
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
