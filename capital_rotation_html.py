"""Render a safe, static, read-only Capital Rotation research report.

No Flask, JavaScript, network, trading, or production route integration.
Accepts only the evaluated report dict; escapes all dynamic content.
"""
from html import escape
from pathlib import Path


def render_rotation_html(report):
    if not isinstance(report, dict) or not isinstance(report.get("result"), dict):
        raise ValueError("invalid report")
    result = report["result"]
    status = result.get("status", "BLOCKED")
    if status not in ("BLOCKED", "RESEARCH_ONLY"):
        raise ValueError("unexpected report status")
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("invalid candidates")
    # A blocked result must never display stale candidate rows.
    if status == "BLOCKED":
        candidates = []
    rows = []
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("invalid candidate")
        symbol = escape(str(item.get("symbol", "")))
        five = escape(str(item.get("relative_5d_pct", "—")))
        twenty = escape(str(item.get("relative_20d_pct", "—")))
        rows.append(f"<tr><td>{symbol}</td><td>{five}</td><td>{twenty}</td></tr>")
    if not rows:
        rows.append('<tr><td colspan="3">No confirmed candidates / insufficient data</td></tr>')
    def field(value):
        return escape(str(value if value is not None else "—"))
    comparison_rows = []
    comparison = report.get('reference_verification', {})
    if comparison.get('status') == 'SPOT_CHECK_ONLY':
        for check in comparison.get('checks', []):
            comparison_rows.append('<tr><td>' + field(check.get('symbol'))
                + '</td><td>' + field(round(check['returns']['5d']['difference_pp'], 4))
                + '</td><td>' + field(round(check['returns']['20d']['difference_pp'], 4)) + '</td></tr>')
    external_section = ''
    if comparison_rows:
        external_section = ('<section><h2>External sample differences</h2>'
            '<p>IEX return minus external published-close return, in percentage points. '
            'Samples only; adjustment and close conventions still require reconciliation.</p>'
            '<table><thead><tr><th>ETF</th><th>5D difference (pp)</th><th>20D difference (pp)</th></tr></thead>'
            '<tbody>' + ''.join(comparison_rows) + '</tbody></table></section>')
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capital Rotation Research</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#172033;background:#f7f9fc}
h1{font-size:1.6rem}section{background:white;border:1px solid #dbe1e9;border-radius:12px;padding:18px;margin:16px 0}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:12px;border-bottom:1px solid #e3e7ee}
small{color:#526074}strong{color:#173b6c}
</style></head><body>
<h1>Capital Rotation — Research Only</h1>
<section><p><strong>Status:</strong> """ + field(status) + """</p>
<p><strong>Regime:</strong> """ + field(result.get("regime")) + """</p>
<p><strong>Reason:</strong> """ + field(result.get("reason", result.get("note"))) + """</p>
<p><strong>Completed session:</strong> """ + field(report.get("expected_session")) + """</p>
<p><strong>Generated UTC:</strong> """ + field(report.get("generated_utc")) + """</p></section>
<p><strong>Data feed:</strong> """ + field(report.get("feed")) + """ (IEX is partial-market data; not consolidated US coverage.)</p>
<section><h2>Validation</h2>
<p><strong>Calculation audit:</strong> """ + field(report.get('calculation_audit', {}).get('status', 'NOT_RUN')) + """</p>
<p><strong>IEX / SIP comparison:</strong> """ + field(report.get('cross_feed_verification', {}).get('status', 'NOT_RUN')) + """</p>
<p><strong>External price sample:</strong> """ + field(report.get('reference_verification', {}).get('status', 'NOT_RUN')) + """</p>
<p><strong>Consecutive observed sessions:</strong> """ + field(report.get('history_summary', {}).get('consecutive_sessions', 0)) + """ / 5 pilot target</p>
<p>Spot checks cover selected symbols and dates only. Five observed sessions do not establish predictive performance or production readiness.</p>
<p>Calculations can be checked from saved closing prices. SIP comparison uses a different feed
from the same provider; it is not an independent vendor verification.</p>
<p><strong>Calendar:</strong> """ + field(report.get('calendar', {}).get('coverage')) + """</p></section>
<section><h2>Relative strength candidates</h2>
<table><thead><tr><th>ETF</th><th>vs SPY 5D (%)</th><th>vs SPY 20D (%)</th></tr></thead>
<tbody>""" + "".join(rows) + """</tbody></table></section>
""" + external_section + """
<small>Price-relative strength proxy only. Not actual fund flows, investment advice,
or a trading signal. Data may be delayed or incomplete. No automated orders.</small>
</body></html>"""


def save_rotation_html(report, output_path):
    path = Path(output_path)
    path.write_text(render_rotation_html(report), encoding="utf-8")
    return path
