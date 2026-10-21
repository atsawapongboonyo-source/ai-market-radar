"""Browser QA using explicitly SYNTHETIC fixtures. Never an observed market signal."""
from pathlib import Path
import sys,json,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import Flask,render_template
from playwright.sync_api import sync_playwright
from test_rotation_stock import NOW,universe,histories
from test_rotation_web import fake_public
from rotation_stock_engine import analyze
from rotation_public_protocol import parse_public
base=fake_public(NOW);_,result=parse_public(json.dumps(base).encode(),NOW)
ranking=[{'symbol':s,'return_5d_pct':base['returns']['5d'][s],'return_20d_pct':base['returns']['20d'][s],'relative_20d_pct':0} for s in base['returns']['5d']]
data={'simulated':True,'result':result,'ranking':ranking,**base}
app=Flask('qa',template_folder=str(Path(__file__).resolve().parents[1]/'rotation_templates'))
with app.app_context():html=render_template('rotation_dashboard.html',data=data,storage_mode='TEST_ONLY',stock_data={'status':'RESEARCH_ONLY','stocks':[analyze('TEST','XLE',histories(),universe(),NOW)]},stock_universe=universe())
with sync_playwright() as p:
    browser=p.chromium.launch()
    for width in (320,390):
        page=browser.new_page(viewport={'width':width,'height':844});page.set_content(html)
        page.locator('details').filter(has=page.locator('summary strong',has_text='XLE')).locator('summary').click()
        assert page.locator('details[open] .stock-card').count()==1
        assert page.evaluate('document.documentElement.scrollWidth')<=width
        assert page.get_by_text('SIMULATED STAGING',exact=False).count()>=1
        page.locator('details[open]').scroll_into_view_if_needed()
        page.screenshot(path=f'rotation-stock-mobile-{width}.png',full_page=True)
        print(json.dumps({'viewport':width,'horizontal_page_overflow':False,'native_expand':True,'simulation_only':True}))
        page.close()
    browser.close()
