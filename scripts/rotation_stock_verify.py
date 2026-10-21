"""Local-only independent Decimal audit. Prints aggregates, never OHLCV or secrets."""
import sys,json,hashlib,os
from decimal import Decimal
from datetime import date,datetime,timezone
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'runtime'))
from rotation_stock_protocol import parse_stock,stock_headers,verify_stock
from rotation_publisher import load_signing_key
from capital_rotation_calendar import trailing_sessions,last_completed_session
from urllib.request import urlopen

def main():
    assert not os.environ.get('ALPACA_DATA_KEY_ID') and not os.environ.get('ALPACA_DATA_SECRET_KEY')
    now=datetime.now(timezone.utc);u=json.loads((root/'runtime'/'data'/'rotation-stock-universe-v1.json').read_text())
    v=json.loads((root/'public-summary.json').read_text());raw=json.dumps(v,sort_keys=True,separators=(',',':')).encode();parse_stock(raw,now,u)
    history=json.loads((root/'local-history.json').read_text());days=[str(d) for d in trailing_sessions(last_completed_session(now),120)]
    for rows in history.values():assert [r['session'] for r in rows]==days
    assert hashlib.sha256(json.dumps(history,sort_keys=True).encode()).hexdigest()==v['audit_sha256']
    checks=0
    for row in v['stocks']:
        m=row['metrics']
        if m is None:continue
        for window,n in [('5d',5),('20d',20)]:
            for symbol,field in [(row['symbol'],'return_'+window+'_pct'),(row['parent'],'etf_'+window+'_pct'),('SPY','spy_'+window+'_pct')]:
                c=[Decimal(str(r['c'])) for r in history[symbol]];expected=(c[-1]/c[-1-n]-1)*100
                assert abs(expected-Decimal(str(m[field])))<Decimal('0.000001');checks+=1
    key=load_signing_key(root.parent/'secrets'/'rotation-staging-real-signing.dpapi')
    h=stock_headers(raw,key,'windows-staging-real',now)
    public=json.loads((root/'runtime'/'rotation-staging-public.json').read_text())['public_keys']
    verify_stock(raw,h,public,now)
    with urlopen('https://ai-market-radar-rotation-staging.onrender.com/api/rotation',timeout=30) as r:baseline=json.load(r)
    assert baseline['session_date']==v['session_date'] and len(baseline['ranking'])==14
    for row in v['stocks']:
        if row['metrics']:
            for w in ('5d','20d'):
                assert abs(row['metrics']['etf_'+w+'_pct']-baseline['returns'][w][row['parent']])<1e-5
                assert abs(row['metrics']['spy_'+w+'_pct']-baseline['returns'][w]['SPY'])<1e-5
    print(json.dumps({'status':'VERIFIED','session':v['session_date'],'history_symbols':len(history),'sessions_each':len(days),'decimal_checks':checks,
        'membership_rows':len(v['stocks']),'public_bytes':len(raw),'actual_staging_baseline_match':True,'signature_verified_locally':True,
        'feature_upload_performed':False,'private_bars_uploaded':False,'rule_version':v['stocks'][0]['rule_version']}))
try:main()
except Exception:print('{"status":"BLOCKED","reason":"INDEPENDENT_STOCK_AUDIT_FAILED"}');sys.exit(2)
