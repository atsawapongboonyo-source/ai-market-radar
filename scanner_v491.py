"""
AI MARKET RADAR V4.9.1

UI hardening patch on top of V4.9.
- force visible version labels after legacy V4.7/V4.7.1 scripts finish
- guarantee Explosive Movers card exists even if HTML marker injection misses
- keep V4.9 backend / API unchanged
"""

import scanner_v49 as v49

app = v49.app


_V491_UI = r'''
<style id="v491Styles">
.v491ExplosiveGrid{display:grid;gap:10px;margin-top:12px}
.v491ExplosiveCard{background:#10263c;border:1px solid #3b536b;border-radius:16px;padding:13px}
.v491ExplosiveCard.hot{border-color:#a16b28}
.v491ExplosiveCard.extreme{border-color:#9b3e3e;box-shadow:0 0 0 1px rgba(255,90,90,.08) inset}
.v491ExplosiveHead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.v491ExplosiveTicker{font-size:21px;font-weight:900}
.v491ExplosiveScore{font-size:26px;font-weight:900;text-align:right}
.v491ExplosiveMetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.v491ExplosiveMetric{background:#132c44;border-radius:11px;padding:9px}
.v491ExplosiveMetric span{display:block;color:#9eb1c6;font-size:10px}
.v491ExplosiveMetric b{display:block;font-size:15px;margin-top:2px}
.v491ExplosiveFlags{margin-top:9px;color:#cbd9e8;font-size:11px;line-height:1.55}
@media(max-width:650px){.v491ExplosiveMetrics{grid-template-columns:1fr 1fr}}
</style>
<script>
(function(){
  function compact(v){
    const n=Number(v);
    if(!Number.isFinite(n))return '—';
    if(n>=1e9)return (n/1e9).toFixed(2)+'B';
    if(n>=1e6)return (n/1e6).toFixed(1)+'M';
    if(n>=1e3)return (n/1e3).toFixed(0)+'K';
    return n.toFixed(0);
  }

  function num(v,d=2){
    const n=Number(v);
    return Number.isFinite(n)?n.toFixed(d):'—';
  }

  function ensureExplosiveCard(){
    if(document.getElementById('explosiveRadarCard')) return;

    const cards=[...document.querySelectorAll('.card')];
    const topCard=cards.find(c=>
      (c.textContent||'').includes('Top Pick Engine')
    );
    if(!topCard) return;

    const card=document.createElement('div');
    card.className='card';
    card.id='explosiveRadarCard';
    card.innerHTML=`
      <h2>🔥 Explosive Movers Radar</h2>
      <div class="small">
        แยกจาก Top Pick ปกติ • หา RETO-like momentum จาก Price + Volume + Gap + Liquidity + Small-cap proxy<br>
        <b>Explosion Score ไม่ใช่เปอร์เซ็นต์ชนะและไม่ใช่คำสั่งซื้อ</b>
      </div>
      <button style="margin-top:12px" id="v491ExplosiveBtn">🔥 สแกน Explosive Movers</button>
      <div id="explosiveStatus" class="status info">กดสแกนเมื่ออยากหา Volume / Squeeze ผิดปกติ</div>
      <div id="explosiveGrid" class="v491ExplosiveGrid"></div>
    `;
    topCard.insertAdjacentElement('afterend',card);

    document.getElementById('v491ExplosiveBtn').addEventListener('click',()=>loadExplosiveMoversV491(true));
  }

  async function loadExplosiveMoversV491(force){
    const st=document.getElementById('explosiveStatus');
    const grid=document.getElementById('explosiveGrid');
    if(!st||!grid)return;
    st.className='status info';
    st.textContent='กำลังค้นหา Small-cap / Volume ignition...';
    try{
      const r=await fetch(force?'/api/explosive-movers?force=1':'/api/explosive-movers',{cache:'no-store'});
      const j=await r.json();
      if(!r.ok||!j.ok)throw Error(j.error||('HTTP '+r.status));
      const d=j.data||{};
      const arr=d.movers||[];
      st.className='status '+(arr.length?'good':'warn');
      st.textContent=`V4.9.1 • พบ ${d.total_ranked??0} ตัว • แสดง ${arr.length} ตัว • ${d.from_cache?'Cache':'Fresh scan'}`;
      grid.innerHTML=arr.map((x,i)=>{
        const cls=x.state==='EXTREME'?'extreme':x.state==='HOT'?'hot':'';
        const flags=(x.risk_flags||[]).length?(x.risk_flags||[]).map(v=>`⚠ ${v}`).join(' • '):'ยังไม่มี Risk flag เพิ่ม';
        return `<div class="v491ExplosiveCard ${cls}">
          <div class="v491ExplosiveHead">
            <div><div class="v491ExplosiveTicker">${i+1}. ${x.ticker}</div><div class="small">${x.state_label||''} • ${x.phase_label||''}</div></div>
            <div><div class="small" style="text-align:right">Explosion Score</div><div class="v491ExplosiveScore">${x.explosion_score??'—'}</div></div>
          </div>
          <div class="v491ExplosiveMetrics">
            <div class="v491ExplosiveMetric"><span>Change</span><b>${Number(x.change_pct)>=0?'+':''}${num(x.change_pct)}%</b></div>
            <div class="v491ExplosiveMetric"><span>RVOL</span><b>${x.rvol==null?'—':num(x.rvol)+'x'}</b></div>
            <div class="v491ExplosiveMetric"><span>Volume</span><b>${compact(x.volume)}</b></div>
            <div class="v491ExplosiveMetric"><span>Market Cap</span><b>${compact(x.market_cap)}</b></div>
            <div class="v491ExplosiveMetric"><span>Gap</span><b>${x.gap_pct==null?'—':(Number(x.gap_pct)>=0?'+':'')+num(x.gap_pct)+'%'}</b></div>
            <div class="v491ExplosiveMetric"><span>Day Range</span><b>${x.range_pct==null?'—':num(x.range_pct)+'%'}</b></div>
            <div class="v491ExplosiveMetric"><span>$ Volume</span><b>${compact(x.dollar_volume)}</b></div>
            <div class="v491ExplosiveMetric"><span>Chase Risk</span><b>${x.chase_label||'—'}</b></div>
          </div>
          <div class="v491ExplosiveFlags">${flags}</div>
        </div>`;
      }).join('');
    }catch(e){
      st.className='status bad';
      st.textContent='Explosive Radar โหลดไม่สำเร็จ: '+e.message;
      grid.innerHTML='';
    }
  }

  window.loadExplosiveMoversV491=loadExplosiveMoversV491;

  function applyV491(){
    document.title='AI Market Radar V4.9.1';

    const header=document.querySelector('.head .mut');
    if(header) header.textContent='V4.9.1 • Leading Signal + Explosive Movers';

    const firstCard=[...document.querySelectorAll('.card')].find(c=>
      (c.textContent||'').includes('วันนี้ดูตัวไหนก่อน')
    );
    if(firstCard){
      const info=[...firstCard.querySelectorAll('.status.info')].find(x=>
        /V4\.7|V4\.6|Position Engine/.test(x.textContent||'')
      );
      if(info){
        info.innerHTML='<b>V4.9.1</b> Leading Signal + Position Engine + Explosive Movers<br>Scanner + Catalyst + Premarket Gate + Opening Confirmation เดิมยังอยู่ครบ';
      }
    }

    const positionCard=document.getElementById('positionCard');
    if(positionCard){
      const pill=positionCard.querySelector('.versionPill');
      if(pill) pill.textContent='V4.9.1';
    }

    ensureExplosiveCard();
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',()=>setTimeout(applyV491,0));
  }else{
    setTimeout(applyV491,0);
  }
})();
</script>
'''


# V5.0 owns presentation. Keep V4.9.1 backend/helpers loaded, but do not
# rewrite HTML responses or inject legacy version scripts.
