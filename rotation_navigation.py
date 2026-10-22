"""Presentation only. Installed by the staging entrypoint, never scanner:app."""
from flask import request

LINKS = (('Home', '/'), ('Scanner', '/scanner'), ('Rotation', '/rotation'),
         ('Stock Radar', '/stock-radar'), ('Top Pick', '/scanner#top-pick'),
         ('Position', '/scanner#position'))

STYLE = '''<style id="radar-unified-style">
#capital-rotation-nav{box-sizing:border-box;background:#0d1b2a;color:#edf4ff;border-bottom:1px solid #26425d;padding:12px;position:relative;z-index:100001;font:14px system-ui,sans-serif}
#capital-rotation-nav .radar-links{display:flex;flex-wrap:wrap;gap:6px;max-width:1100px;margin:auto}
#capital-rotation-nav a{box-sizing:border-box;display:flex;align-items:center;justify-content:center;min-height:44px;padding:8px 14px;border:1px solid #31526d;border-radius:10px;color:#b9deff;text-decoration:none}
#capital-rotation-nav a[aria-current]{background:#204f76;color:white;border-color:#8bc4ff}
#capital-rotation-nav a:focus-visible{outline:3px solid #ffd166;outline-offset:2px}
#capital-rotation-nav .radar-context{max-width:1100px;margin:8px auto 0;font-size:12px;line-height:1.5;color:#a2b5cd}
#capital-rotation-nav .radar-production{display:inline-flex;padding:0 4px;border:0;text-decoration:underline}
body.radar-unified #v500StaticNav{display:none!important}
body.radar-unified{padding-bottom:24px!important}
body.radar-unified .card,body.radar-unified .openingCard{scroll-margin-top:16px;min-width:0;overflow-wrap:anywhere}
body.radar-unified input,body.radar-unified select{min-width:0;max-width:100%;box-sizing:border-box}
@media(max-width:600px){#capital-rotation-nav .radar-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}#capital-rotation-nav a{padding:8px 4px;font-size:12px}body.radar-unified .grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''

def navigation(path):
    links = ''.join('<a href="'+url+'"'+(' aria-current="page"' if url == path else '')+'>'+label+'</a>'
                    for label, url in LINKS)
    return ('<nav id="capital-rotation-nav" aria-label="AI Market Radar"><div class="radar-links">'+links+
            '</div><div class="radar-context">STAGING · Top Pick / Position อยู่ใน Scanner · '
            '<a class="radar-production" href="https://ai-market-radar-h08w.onrender.com/" target="_blank" rel="noopener noreferrer">เปิด Production ในแท็บใหม่ ↗</a>'
            ' · กลับมาที่แท็บนี้เพื่อใช้ Rotation</div></nav>')

SCRIPT = '''<script id="radar-unified-history">
(function(){
 function sync(){
  var hash=location.hash, path=location.pathname;
  document.querySelectorAll('#capital-rotation-nav .radar-links a').forEach(function(a){
   var active=a.getAttribute('href')===path+hash;
   if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
  });
  if(path!=='/'&&path!=='/scanner')return;
  if(window.v510ClosePosition)window.v510ClosePosition();
  if(hash==='#position'){
   if(window.v510OpenPosition)window.v510OpenPosition();
  }else if(hash==='#top-pick'){
   var el=document.getElementById('topPicks');
   if(el){el=el.closest('.card')||el;el.style.setProperty('display','block','important');el.scrollIntoView();}
  }
 }
 function boot(){
  var close=document.getElementById('v510PositionClose');
  if(close)close.addEventListener('click',function(){if(location.hash==='#position')location.hash='';});
  sync();
 }
 window.addEventListener('hashchange',sync);window.addEventListener('pageshow',sync);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();</script>'''

def install_navigation(app, *, scanner=False):
    @app.after_request
    def unified_navigation(response):
        if (request.path not in ('/', '/scanner', '/analysis', '/rotation', '/stock-radar') or
                response.status_code != 200 or response.mimetype != 'text/html' or response.direct_passthrough):
            return response
        import re
        body = response.get_data(as_text=True)
        # Existing scanner markup has presentation CSS inside its Position JS.
        # Move only that exact CSS block into a style element so the existing
        # Position functions can load. No engine/decision code is rewritten.
        misplaced = re.search(r'(?m)^\.v5PosHero\{.*?^@media\(max-width:560px\)\{\.positionCard \.positionGrid\{grid-template-columns:1fr 1fr\}\}', body, re.S)
        if scanner and misplaced:
            css = misplaced.group(0)
            body = body[:misplaced.start()]+body[misplaced.end():]
            body = body.replace('</head>', '<style id="radar-position-css-repair">'+css+'</style></head>', 1)
        body = re.sub(r'<nav id="capital-rotation-nav".*?</nav>', '', body, flags=re.S)
        if request.path == '/rotation':
            body = re.sub(r'<nav aria-label="Navigation">.*?</nav>', '', body, flags=re.S)
        body = body.replace('</head>', STYLE+'</head>', 1)
        body = body.replace('<body>', '<body class="radar-unified">'+navigation(request.path), 1)
        if scanner:
            # Legacy scanner includes a literal </body> inside an HTML comment.
            before, closing, after = body.rpartition('</body>')
            body = before+SCRIPT+closing+after if closing else body+SCRIPT
        response.set_data(body)
        return response
