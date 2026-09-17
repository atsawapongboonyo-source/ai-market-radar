"""
AI MARKET RADAR V4.9.2

Final UI/cache hardening on top of V4.9.1.

Why this layer exists:
- some mobile browsers can keep an older rendered HTML page
- legacy V4.7/V4.7.1 JavaScript can rewrite the visible version after load
- Flask after_request hooks execute in reverse registration order, so a newer
  response patch can be followed by an older hook

V4.9.2 therefore:
- wraps the actual home/scanner view functions and injects the latest UI there
- disables browser/proxy caching for HTML/API responses
- runs a small finalizer after DOM load (and a few delayed passes) so legacy
  version text cannot remain visible
- keeps all V4.9 Explosive Movers APIs and scoring unchanged
"""

import scanner_v491 as v491

app = v491.app


_FINALIZER = r'''
<script id="v492Finalizer">
(function(){
  function applyFinal(){
    document.title='AI Market Radar V4.9.2';

    const header=document.querySelector('.head .mut');
    if(header){
      header.textContent='V4.9.2 • Leading Signal + Explosive Movers';
    }

    const cards=[...document.querySelectorAll('.card')];
    const firstCard=cards.find(c=>(c.textContent||'').includes('วันนี้ดูตัวไหนก่อน'));
    if(firstCard){
      const info=[...firstCard.querySelectorAll('.status.info')].find(x=>
        /V4\.7|V4\.6|Position Engine|Leading Signal/.test(x.textContent||'')
      );
      if(info){
        info.innerHTML='<b>V4.9.2</b> Leading Signal + Position Engine + Explosive Movers<br>Scanner + Catalyst + Premarket Gate + Opening Confirmation เดิมยังอยู่ครบ';
      }
    }

    const positionCard=document.getElementById('positionCard');
    if(positionCard){
      const pill=positionCard.querySelector('.versionPill');
      if(pill) pill.textContent='V4.9.2';
    }

    if(typeof window.loadExplosiveMoversV491==='function'){
      const existing=document.getElementById('explosiveRadarCard');
      if(!existing){
        const topCard=cards.find(c=>(c.textContent||'').includes('Top Pick Engine'));
        if(topCard){
          const card=document.createElement('div');
          card.className='card';
          card.id='explosiveRadarCard';
          card.innerHTML=`
            <h2>🔥 Explosive Movers Radar</h2>
            <div class="small">
              แยกจาก Top Pick ปกติ • หา RETO-like momentum จาก Price + Volume + Gap + Liquidity + Small-cap proxy<br>
              <b>Explosion Score ไม่ใช่เปอร์เซ็นต์ชนะและไม่ใช่คำสั่งซื้อ</b>
            </div>
            <button style="margin-top:12px" id="v492ExplosiveBtn">🔥 สแกน Explosive Movers</button>
            <div id="explosiveStatus" class="status info">กดสแกนเมื่ออยากหา Volume / Squeeze ผิดปกติ</div>
            <div id="explosiveGrid" class="v491ExplosiveGrid"></div>`;
          topCard.insertAdjacentElement('afterend',card);
          const btn=document.getElementById('v492ExplosiveBtn');
          if(btn) btn.addEventListener('click',()=>window.loadExplosiveMoversV491(true));
        }
      }
    }
  }

  function boot(){
    applyFinal();
    setTimeout(applyFinal,100);
    setTimeout(applyFinal,500);
    setTimeout(applyFinal,1200);
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',boot,{once:true});
  }else{
    boot();
  }
})();
</script>
'''


def _inject_latest_html(value):
    response = app.make_response(value)

    try:
        if 'text/html' in (response.content_type or '').lower():
            body = response.get_data(as_text=True)

            # Route-level injection occurs before global after_request hooks.
            # The script itself is intentionally placed last in the body so it
            # runs after all legacy inline scripts in scanner.html.
            if 'v491Styles' not in body:
                body = body.replace('</body>', v491._V491_UI + '\n</body>', 1)

            if 'v492Finalizer' not in body:
                body = body.replace('</body>', _FINALIZER + '\n</body>', 1)

            response.set_data(body)
            response.headers['Content-Length'] = str(len(response.get_data()))
    except Exception:
        pass

    return response


_old_home = app.view_functions.get('home')
_old_scanner_page = app.view_functions.get('scanner_page')


if _old_home:
    def home_v492(*args, **kwargs):
        return _inject_latest_html(_old_home(*args, **kwargs))
    app.view_functions['home'] = home_v492


if _old_scanner_page:
    def scanner_page_v492(*args, **kwargs):
        return _inject_latest_html(_old_scanner_page(*args, **kwargs))
    app.view_functions['scanner_page'] = scanner_page_v492


@app.after_request
def _v492_no_cache(response):
    try:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    except Exception:
        pass
    return response
