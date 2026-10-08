"""
AI Market Radar V5.3 - Server Auto Monitor.

Isolated runtime extension over V5.2.
Existing Scanner, ranking, Premarket Gate, Opening Confirmation, Final Decision,
Position Engine, Multi-Radar and browser Trigger Monitor remain authoritative.
"""

import scanner_v520 as v520
from flask import jsonify

from server_auto_monitor import start_server_monitor, status as server_monitor_status

app = v520.app


@app.route("/api/server-monitor-status")
def _v530_server_monitor_status_api():
    return jsonify({"ok": True, "version": "5.3", "data": server_monitor_status()})


# Starts only when SERVER_AUTO_MONITOR_ENABLED=1.
# The worker is daemonized and alert-only; it never submits orders.
start_server_monitor()


_V530_UI = r"""
<style id="v530ServerMonitorStyle">
.v530Card{margin-top:14px;border:1px solid #315a7e;border-radius:18px;padding:14px;background:#0b2135}
.v530Head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.v530Badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#103421;border:1px solid #28724b;color:#bfe9cf}
.v530Grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.v530Box{background:#112b43;border-radius:13px;padding:10px}.v530Box span{display:block;font-size:10px;color:#9eb1c6}.v530Box b{display:block;margin-top:3px;font-size:14px}
.v530Rows{display:grid;gap:7px;margin-top:10px}.v530Row{background:#10263c;border:1px solid #24425f;border-radius:11px;padding:9px;font-size:11px}
@media(max-width:560px){.v530Grid{grid-template-columns:1fr}}
</style>
<script id="v530ServerMonitor">
(function(){
  function esc(v){return String(v==null?'—':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function ensure(){
    if(document.getElementById('v530ServerMonitorCard'))return;
    var anchor=document.getElementById('v520TriggerCard')||document.getElementById('finalDash');
    if(!anchor)return;
    var card=document.createElement('section');
    card.id='v530ServerMonitorCard';card.className='v530Card';
    card.innerHTML='<div class="v530Head"><div><b>☁ Server Auto Monitor</b><div class="small" style="margin-top:4px">เฝ้าสัญญาณบน Render แม้ปิดหน้า Scanner</div></div><span class="v530Badge">V5.3</span></div>'+
      '<div class="v530Grid">'+
      '<div class="v530Box"><span>SERVER</span><b id="v530Running">—</b></div>'+
      '<div class="v530Box"><span>SESSION</span><b id="v530Session">—</b></div>'+
      '<div class="v530Box"><span>LAST CHECK</span><b id="v530Last">—</b></div>'+
      '</div><div id="v530Rows" class="v530Rows"><div class="small">กำลังอ่านสถานะ...</div></div>'+
      '<div class="v520Note">Alert only • Fail closed • เริ่มประเมินหลัง Opening Range 15 นาที • ไม่มี Auto Order</div>';
    anchor.parentNode.insertBefore(card,anchor.nextSibling);
  }
  async function load(){
    ensure();
    try{
      var r=await fetch('/api/server-monitor-status',{cache:'no-store'}),j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
      var x=j.data||{};
      var a=document.getElementById('v530Running'),s=document.getElementById('v530Session'),l=document.getElementById('v530Last'),rows=document.getElementById('v530Rows');
      if(a)a.textContent=x.enabled?(x.running?'🟢 RUNNING':'🟡 STARTING'):'⚪ DISABLED';
      if(s)s.textContent=x.session||'—';
      if(l)l.textContent=x.last_cycle_at?new Date(x.last_cycle_at).toLocaleTimeString():'—';
      if(rows){
        var cs=x.candidates||[];
        rows.innerHTML=cs.length?cs.map(function(c){
          var p=c.snapshot&&c.snapshot.price!=null?Number(c.snapshot.price).toFixed(2):'—';
          return '<div class="v530Row"><b>'+esc(c.ticker)+'</b> • '+esc(c.state)+' • $'+esc(p)+'</div>';
        }).join(''):'<div class="small">ไม่มี Candidate ในรอบนี้ / ตลาดยังไม่อยู่ช่วง Monitor</div>';
      }
    }catch(e){
      var rows=document.getElementById('v530Rows');if(rows)rows.innerHTML='<div class="small">อ่าน Server Monitor ไม่ได้: '+esc(e.message)+'</div>';
    }
  }
  function boot(){ensure();load();setInterval(load,30000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(function(){ensure();load()},1200);
})();
</script>
"""


@app.after_request
def _v530_inject_server_monitor(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v530ServerMonitor" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _V530_UI + "\n" + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response
