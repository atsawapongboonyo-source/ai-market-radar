"""
AI Market Radar V5.3.1 - Premarket Prep + Live Candidate Rotation UI.

Presentation-only extension over V5.3. Decision formulas remain unchanged.
"""

import scanner_v530 as v530

app = v530.app


_V531_UI = r"""
<style id="v531LiveRotationStyle">
.v531Card{margin-top:14px;border:1px solid #315a7e;border-radius:18px;padding:14px;background:#0b2135}
.v531Head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.v531Badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:20px;background:#173d5e;border:1px solid #39749f;color:#c9e4f8}
.v531Grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.v531Box{background:#112b43;border-radius:13px;padding:10px}.v531Box span{display:block;font-size:10px;color:#9eb1c6}.v531Box b{display:block;margin-top:4px;font-size:14px}
.v531Rows{display:grid;gap:7px;margin-top:10px}.v531Row{background:#10263c;border:1px solid #24425f;border-radius:11px;padding:9px;font-size:11px;line-height:1.45}
.v531Tag{display:inline-block;margin-left:5px;padding:2px 6px;border-radius:10px;background:#153a5b;color:#bcd3e8;font-size:9px;font-weight:900}
@media(max-width:560px){.v531Grid{grid-template-columns:1fr}}
</style>
<script id="v531LiveRotation">
(function(){
  function esc(v){return String(v==null?'—':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function money(v){var n=Number(v);return Number.isFinite(n)?'$'+n.toFixed(2):'—'}
  function pct(v){var n=Number(v);return Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'%':'—'}
  function ensure(){
    if(document.getElementById('v531LiveRotationCard'))return;
    var anchor=document.getElementById('v530ServerMonitorCard')||document.getElementById('v520TriggerCard');
    if(!anchor)return;
    var card=document.createElement('section');card.id='v531LiveRotationCard';card.className='v531Card';
    card.innerHTML='<div class="v531Head"><div><b>🌅 Premarket + Live Top Pick</b><div class="small" style="margin-top:4px">เตรียม Candidate ก่อนเปิด • Re-rank ระหว่างตลาด • กันอันดับสลับถี่</div></div><span class="v531Badge">V5.3.1</span></div>'+
      '<div class="v531Grid">'+
      '<div class="v531Box"><span>MODE</span><b id="v531Mode">—</b></div>'+
      '<div class="v531Box"><span>ACTIVE QUEUE</span><b id="v531Queue">—</b></div>'+
      '<div class="v531Box"><span>RE-RANK</span><b id="v531Rerank">—</b></div>'+
      '</div>'+
      '<div id="v531Rows" class="v531Rows"><div class="small">กำลังอ่าน Candidate Queue...</div></div>'+
      '<div class="v520Note">Premarket ไม่ส่ง Entry Alert • หลัง 09:45 ET ตัวใหม่ต้องชนะด้วย margin + ยืนยันหลายรอบก่อนแทนตัวเดิม • Trigger ที่เริ่มทำงานแล้วจะไม่ถูกสลับออกเพราะอันดับแกว่งเล็กน้อย</div>';
    anchor.parentNode.insertBefore(card,anchor.nextSibling);
  }
  async function load(){
    ensure();
    try{
      var r=await fetch('/api/server-monitor-status',{cache:'no-store'}),j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
      var x=j.data||{},mode=document.getElementById('v531Mode'),queue=document.getElementById('v531Queue'),rr=document.getElementById('v531Rerank'),rows=document.getElementById('v531Rows');
      if(mode)mode.textContent=x.candidate_mode||x.session||'—';
      var aq=x.active_queue||[];
      if(queue)queue.textContent=aq.length?aq.map(function(q){return q.ticker}).join(' • '):'—';
      if(rr)rr.textContent=(x.rerank_seconds?Math.round(x.rerank_seconds/60)+' min':'—')+' • Margin '+esc(x.switch_margin||'—');
      var pm=x.premarket||[],live=x.candidates||[];
      var source=pm.length?pm:live;
      if(rows){
        rows.innerHTML=source.length?source.map(function(c){
          var snap=c.snapshot||{},extra=pm.length?(' • PM '+pct(snap.premarket_pct)+' • H/L '+money(snap.premarket_high)+' / '+money(snap.premarket_low)):(' • '+money(snap.price));
          return '<div class="v531Row"><b>'+esc(c.ticker)+'</b><span class="v531Tag">'+esc(c.state)+'</span>'+extra+'<br><span class="small">Watch '+esc(c.watch_score)+' • Buy '+money(c.buy_low)+'–'+money(c.buy_high)+'</span></div>';
        }).join(''):'<div class="small">ยังไม่มี Active Candidate ในช่วงนี้</div>';
      }
    }catch(e){
      var rows=document.getElementById('v531Rows');if(rows)rows.innerHTML='<div class="small">อ่าน Live Rotation ไม่ได้: '+esc(e.message)+'</div>';
    }
  }
  function boot(){ensure();load();setInterval(load,30000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(function(){ensure();load()},1400);
})();
</script>
"""


@app.after_request
def _v531_inject_live_rotation(response):
    try:
        if "text/html" in (response.content_type or "").lower():
            body = response.get_data(as_text=True)
            if "v531LiveRotation" not in body:
                pos = body.lower().rfind("</body>")
                if pos >= 0:
                    body = body[:pos] + _V531_UI + "\n" + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        pass
    return response
