"""Navigation browser QA. Scanner API calls are blocked; never starts a scan."""
import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url')
parser.add_argument('--chrome')
args = parser.parse_args()
server = None
temporary = tempfile.TemporaryDirectory()
if args.url:
    base = args.url.rstrip('/')
else:
    import scanner
    from rotation_web import RotationSite
    from rotation_navigation import install_navigation
    from werkzeug.serving import make_server
    site = RotationSite(scanner.app, database=str(Path(temporary.name)/'qa.sqlite'), simulated=True)
    install_navigation(scanner.app, scanner=True)
    install_navigation(site.rotation_app)
    server = make_server('127.0.0.1', 0, site, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:'+str(server.server_port)

results = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(**({'executable_path':args.chrome} if args.chrome else {}))
        for width in (320, 390, 1440):
            context = browser.new_context(viewport={'width':width,'height':900})
            # Exercise the real HTML/JS without initiating data downloads or alerts.
            context.route('**/api/**', lambda route: route.fulfill(status=200, content_type='application/json',
                body='{"ok":false,"error":"NAVIGATION_QA_NO_SCAN","data":{}}'))
            page = context.new_page()
            page.on('pageerror', lambda error: print('BROWSER_ERROR', error.stack))
            page.goto(base+'/rotation')
            for label, path in [('Home','/'),('Scanner','/scanner'),('Stock Radar','/analysis'),
                                ('Top Pick','/scanner#top-pick'),('Position','/scanner#position')]:
                nav = page.locator('#capital-rotation-nav')
                assert nav.count()==1
                nav.get_by_role('link',name=label,exact=True).click()
                page.wait_for_url(base+path)
                page.wait_for_timeout(150)
                assert page.locator('#capital-rotation-nav [aria-current="page"]').inner_text()==label, (label,page.url,page.locator('#capital-rotation-nav').inner_text())
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width,path)
                if label=='Top Pick':
                    assert page.locator('#topPicks').locator('xpath=ancestor::*[contains(@class,"card")][1]').is_visible()
                if label=='Position':
                    assert page.locator('#v510PositionPanel').is_visible()
                page.screenshot(path=f'rotation-navigation-{width}-{label.replace(" ","-")}.png',full_page=True)
            page.go_back()
            page.wait_for_url(base+'/scanner#top-pick')
            assert not page.locator('#v510PositionPanel').is_visible()
            page.go_forward()
            page.wait_for_url(base+'/scanner#position')
            assert page.locator('#v510PositionPanel').is_visible()
            page.get_by_role('button',name='ปิด',exact=False).click()
            assert page.url.endswith('/scanner#') or page.url.endswith('/scanner')
            page.locator('#capital-rotation-nav').get_by_role('link',name='Rotation',exact=True).click()
            page.wait_for_url(base+'/rotation')
            assert page.locator('#capital-rotation-nav .radar-production').get_attribute('target')=='_blank'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'rotation-navigation-{width}-Rotation.png',full_page=True)
            results.append({'width':width,'routes':6,'history_back_forward':True,
                            'position_close':True,'no_page_overflow':True,'scanner_api_blocked':True})
            context.close()
        browser.close()
finally:
    if server: server.shutdown()
    temporary.cleanup()
Path('rotation-navigation-results.json').write_text(json.dumps({'url':base,'results':results},indent=2))
print(json.dumps(results))
