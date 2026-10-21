"""Staging response boundary: API bytes and scanner functions stay untouched."""
from flask import Flask
from rotation_navigation import install_navigation

def test_navigation_changes_only_successful_pages_and_repairs_position_css():
    app = Flask('navigation-test')
    markup = '''<html><head></head><body><script>
.v5PosHero{display:none}
@media(max-width:560px){.positionCard .positionGrid{grid-template-columns:1fr 1fr}}
function positionLogic(){return 72;}
</script><!-- literal </body> --></body></html>'''
    app.add_url_rule('/scanner', endpoint='scanner', view_func=lambda:markup)
    app.add_url_rule('/api/scan', endpoint='scan', view_func=lambda:({'score':72},200,{'Cache-Control':'private'}))
    client=app.test_client()
    with app.app_context():
        api=app.make_response(app.view_functions['scan']())
    functions=dict(app.view_functions)
    install_navigation(app, scanner=True)
    assert app.view_functions==functions
    after=client.get('/api/scan')
    assert after.data==api.data and after.headers==api.headers
    page=client.get('/scanner').get_data(as_text=True)
    assert page.count('id="capital-rotation-nav"')==1
    assert 'function positionLogic(){return 72;}' in page
    assert '<style id="radar-position-css-repair">.v5PosHero' in page
    assert page.index('radar-unified-history')>page.index('<!-- literal </body> -->')
    assert '/scanner#position' in page and '/scanner#top-pick' in page
    assert client.get('/missing').status_code==404
