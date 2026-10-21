"""Read-only staging Home projection of validated stock publications."""
from datetime import datetime, timezone, time
from flask import jsonify, request, render_template_string
from capital_rotation_calendar import ny_timezone, is_session, session_close, CalendarError


def opportunities(current, now=None):
    now = now or datetime.now(timezone.utc)
    data = current()  # Existing signature-ingest/schema/session/baseline gates.
    rows = data.get('stocks', []) if data.get('status') == 'RESEARCH_ONLY' else []
    try:
        local = now.astimezone(ny_timezone())
        opened = datetime.combine(local.date(), time(9, 30), ny_timezone())
        session = ('REGULAR' if is_session(local.date()) and opened <= now < session_close(local.date())
                   else 'OUTSIDE_REGULAR')
    except CalendarError:
        session = 'UNKNOWN'
        rows = []
        data = {'reason': 'CALENDAR_UNAVAILABLE'}
    counts = {s: sum(r['state'] == s for r in rows) for s in ('READY', 'WAIT', 'AVOID', 'BLOCKED')}
    cards = []
    for r in sorted(rows, key=lambda r: (r['symbol'], r['parent'])):
        cards.append({'ticker': r['symbol'], 'parent': r['parent'], 'state': r['state'],
            'price': r['metrics']['close'] if r['metrics'] else None,
            'reasons': r['reason_codes'], 'risk_flags': r['warnings'],
            'confidence': 'NOT_CALIBRATED', 'rule_version': r['rule_version']})
    return {'signal': 'Rotation Stock Decision — EOD research', 'scanner_signal': 'Scanner V4.10 — separate signal; not evaluated here',
        'status': next((s for s in ('READY', 'WAIT', 'AVOID') if counts[s]), 'BLOCKED'),
        'reason': data.get('reason', 'NO_READY_SIGNALS' if not counts['READY'] else 'RESEARCH_REVIEW_ONLY'),
        'counts': counts, 'cards': cards, 'session_date': data.get('session_date'),
        'generated_utc': data.get('generated_utc'), 'checked_utc': now.isoformat(),
        'market_session': session, 'source': 'Alpaca IEX · split-adjusted daily close · NOT LIVE · not consolidated SIP',
        'freshness': 'LATEST_COMPLETED_SESSION' if rows else 'BLOCKED',
        'last_quote_utc': None, 'last_trade_utc': None, 'provider_bar_timestamp_utc': None,
        'latency': 'UNKNOWN: quote/trade/provider timestamps are not in the signed contract',
        'guard': {'status': 'UNKNOWN', 'focus': ['MU', 'SNDK', 'AI', 'Memory', 'Optical'],
                  'reason': 'No authorized holdings or signed aligned correlation histories supplied'},
        'trade_signal': False}


TEMPLATE = '''<section id="radar-opportunities" style="box-sizing:border-box;max-width:1100px;margin:16px auto;padding:16px;background:#102033;color:#edf4ff;border-radius:12px;font:14px system-ui;overflow-wrap:anywhere">
<h2>Radar Opportunities · STAGING</h2><p>{{ d.signal }} · read-only · ไม่ส่งคำสั่งซื้อขาย</p>
<p>{{ d.scanner_signal }}</p><p><strong>{{ d.status }}</strong> · {{ d.reason }}</p>
<p>{{ d.source }}</p><p>As-of session: {{ d.session_date or 'UNKNOWN' }} · Published: {{ d.generated_utc or 'UNKNOWN' }} · {{ d.freshness }} · {{ d.market_session }}</p>
<p>READY {{ d.counts.READY }} · WAIT {{ d.counts.WAIT }} · AVOID {{ d.counts.AVOID }} · BLOCKED {{ d.counts.BLOCKED }}</p>
<p>Confidence: NOT_CALIBRATED — ไม่มีค่าความน่าจะเป็นที่พิสูจน์แล้ว<br>{{ d.latency }}</p>
{% for r in d.cards %}<details {% if r.state == 'READY' %}open{% endif %} style="padding:10px 0;border-top:1px solid #31526d"><summary>{{ r.ticker }} / {{ r.parent }} · {{ r.state }} · EOD close {{ r.price if r.price is not none else 'UNKNOWN' }}</summary><p>{{ r.rule_version }} · {{ r.reasons|join(', ') }}</p><p>Risk: {{ r.risk_flags|join(', ') }}</p></details>{% endfor %}
<p>Correlation &amp; Exposure Guard V1 · {{ d.guard.status }} · MU/SNDK · AI/Memory/Optical<br>{{ d.guard.reason }}</p><a style="color:#93c5fd" href="/rotation">ดูรายละเอียด Rotation →</a></section>'''


def install_opportunities(scanner_app, rotation_app, current, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))

    @rotation_app.get('/api/rotation/opportunities')
    def read_opportunities():
        response = jsonify(opportunities(current, clock()))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @scanner_app.after_request
    def home_opportunities(response):
        if request.path == '/' and response.status_code == 200 and response.mimetype == 'text/html':
            panel = render_template_string(TEMPLATE, d=opportunities(current, clock()))
            body = response.get_data(as_text=True)
            # Prepend the read-only panel to Home without altering scanner routes/engines.
            import re
            response.set_data(re.sub(r'(<body\b[^>]*>)', lambda m: m[0] + panel, body, count=1, flags=re.I))
            response.headers['Cache-Control'] = 'no-store'
        return response
