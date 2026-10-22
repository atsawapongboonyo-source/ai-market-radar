"""Staging-only read-only Stock Radar candidate directory. No market-data calls."""
import json
from pathlib import Path
from flask import request, render_template_string
from stock_radar_universe_validation import validate_universe

TEMPLATE = '''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stock Radar V2 Research</title><style>
body{font:15px system-ui,sans-serif;background:#0d1b2a;color:#e8f2ff;margin:0;padding:18px}main{max-width:950px;margin:auto}a{color:#9bcfff}input,select{font:inherit;padding:12px;background:#182c43;color:white;border:1px solid #53728d;border-radius:8px;max-width:100%;box-sizing:border-box}form{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}button{padding:12px;background:#315f88;color:white;border:0;border-radius:8px;cursor:pointer}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #37506a;padding:12px 6px;overflow-wrap:anywhere}small{color:#b6c8dc}p{line-height:1.5}@media(max-width:400px){body{padding:10px}td,th{padding:8px 4px;font-size:13px}}
</style></head><body><main><p><a href="/rotation">← Rotation</a> · <a href="/">Home</a></p><h1>Stock Radar V2 · Research</h1><p>STAGING ONLY · Candidate watchlist, not ETF holdings. No live quotes, no trade signals. All entries are NOT_EVALUATED until independently validated and published.</p><p><small>Verified ETF holdings: {{ report.verified_etf_funds }} funds / {{ report.verified_unique_stocks }} unique stocks · Research: {{ report.research_candidates }} candidates · {{ report.groups }} groups. Overlap is allowed but does not confer a signal.</small></p>
<form method="get" action="/stock-radar"><label>Search <input name="q" value="{{ q }}" maxlength="24" placeholder="Ticker or group"></label><label>Group <select name="group"><option value="">All groups</option>{% for group in groups %}<option value="{{ group }}" {% if group == selected %}selected{% endif %}>{{ group }}</option>{% endfor %}</select></label><button type="submit">Filter</button></form><p>{{ rows|length }} candidates · research only · prices UNKNOWN</p><table><thead><tr><th>Ticker</th><th>Research group</th><th>Decision</th></tr></thead><tbody>{% for group, ticker in rows %}<tr><td><strong>{{ ticker }}</strong></td><td>{{ group }}</td><td>NOT_EVALUATED</td></tr>{% endfor %}</tbody></table>{% if not rows %}<p>No candidates match your filter.</p>{% endif %}<p><small>Source: curated research candidates; ETF holdings are separately verified. No data collection triggered by this page.</small></p></main></body></html>'''


def filtered_rows(watchlist, q='', group=''):
    q = q.strip().casefold()[:24]
    if group not in watchlist['groups']:
        group = ''
    return [(g, ticker) for g, tickers in watchlist['groups'].items()
            if not group or g == group for ticker in tickers
            if not q or q in ticker.casefold() or q in g.casefold()]


def install_research_directory(app, root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    watchlist = json.loads((root/'data/stock-radar-research-watchlist-v1.json').read_text(encoding='utf-8'))
    holdings = json.loads((root/'data/rotation-stock-universe-v1.json').read_text(encoding='utf-8'))
    report = validate_universe(watchlist, holdings)

    @app.get('/stock-radar')
    def research_stock_radar():
        selected = request.args.get('group', '', type=str)[:80]
        q = request.args.get('q', '', type=str)[:24]
        response = app.make_response(render_template_string(TEMPLATE, rows=filtered_rows(watchlist,q,selected),
            groups=watchlist['groups'], selected=selected, q=q, report=report))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
