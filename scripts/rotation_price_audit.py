"""Explicit read-only public HTTP audit; no scans, alerts or orders."""
import hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import requests

s = requests.Session(); s.trust_env = False
out = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'requests': []}
for name, base, paths in [
    ('production', 'https://ai-market-radar-h08w.onrender.com', ['/api/trigger-quote?ticker=MU', '/api/trigger-quote?ticker=SNDK']),
    ('rotation_staging', 'https://ai-market-radar-rotation-staging.onrender.com', ['/api/rotation', '/api/rotation/stocks'])]:
    for path in paths:
        started = time.monotonic()
        try:
            r = s.get(base + path, timeout=70)
            value = r.json()
            item = {'environment': name, 'url': base + path, 'http': r.status_code,
                    'request_elapsed_seconds': round(time.monotonic()-started, 3),
                    'sha256': hashlib.sha256(r.content).hexdigest()}
            if 'trigger-quote' in path:
                item['quote_response'] = value
            else:
                item['snapshot'] = {k: value.get(k) for k in ('status','reason','session_date','generated_utc','feed')}
                if 'stocks' in value:
                    rows=value['stocks'];item['row_count']=len(rows)
                    item['counts']={state:sum(row['state']==state for row in rows) for state in ('READY','WAIT','AVOID','BLOCKED')}
                    item['focus_rows']=[{'symbol':row['symbol'],'parent':row['parent'],'state':row['state'],'close':(row.get('metrics') or {}).get('close')} for row in rows if row['symbol'] in ('MU','SNDK')]
            out['requests'].append(item)
        except Exception as e:
            out['requests'].append({'environment':name,'url':base+path,'error_type':type(e).__name__})
Path('rotation-price-live-audit.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out))
