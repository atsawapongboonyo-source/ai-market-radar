"""Opt-in local IEX collector. GET market-data bars only; no account/order APIs.
Credential-bearing collection and DPAPI-signed publication are separate modes.
Local raw history never leaves Windows. Errors use fixed markers only.
"""
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
import argparse,hashlib,json,os,sys
from urllib.request import Request,build_opener
from urllib.parse import urlencode
from urllib.error import HTTPError
from capital_rotation_alpaca import _NoRedirect,_readonly_urlopen,MarketDataError,HOST
from capital_rotation_calendar import last_completed_session,trailing_sessions
from rotation_stock_engine import analyze,RULE_VERSION
from rotation_stock_protocol import parse_stock,stock_headers,STOCK_PATH,MAX_STOCK_BODY
from rotation_stock_backtest import walk_forward

ENDPOINT='https://ai-market-radar-rotation-staging.onrender.com'+STOCK_PATH

def fetch_history(symbols,day,key,secret,opener=None):
    if not key or not secret:raise MarketDataError('CREDENTIALS_UNAVAILABLE')
    first=trailing_sessions(day,120)[0];out={s:[] for s in symbols};token=None;tokens=set()
    for page in range(8):
        params={'symbols':','.join(sorted(symbols)),'timeframe':'1Day','start':str(first),'end':str(day+timedelta(days=1)),
                'adjustment':'split','feed':'iex','limit':10000,'sort':'asc'}
        if token:params['page_token']=token
        req=Request(HOST+'?'+urlencode(params),headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},method='GET')
        try:
            with (opener or _readonly_urlopen)(req,timeout=25) as r:raw=r.read(8000001)
            if len(raw)>8000000:raise ValueError()
            data=json.loads(raw)
            if not isinstance(data.get('bars'),dict):raise ValueError()
            for s,rows in data['bars'].items():
                if s not in out:raise ValueError()
                for row in rows:
                    ts=datetime.fromisoformat(row['t'].replace('Z','+00:00'))
                    if ts.tzinfo is None or ts.date()>day:raise ValueError()
                    out[s].append({'session':str(ts.date()),**{k:row[k] for k in ('o','h','l','c','v')}})
            token=data.get('next_page_token')
            if not token:return out
            if token in tokens:raise ValueError()
            tokens.add(token)
        except Exception:raise MarketDataError('MARKET_DATA_UNAVAILABLE_OR_INVALID') from None
    raise MarketDataError('PAGINATION_LIMIT')

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,sort_keys=True,allow_nan=False),encoding='utf-8');os.replace(tmp,path)

def collect(root,universe,now,*,fetcher=fetch_history):
    root=Path(root);day=last_completed_session(now)
    symbols={'SPY',*universe['funds']}
    for fund in universe['funds'].values():symbols.update(s['symbol'] for s in fund['stocks'])
    history=fetcher(symbols,day,os.environ.get('ALPACA_DATA_KEY_ID'),os.environ.get('ALPACA_DATA_SECRET_KEY'))
    audit=hashlib.sha256(json.dumps(history,sort_keys=True).encode()).hexdigest()
    rows=[analyze(s['symbol'],p,history,universe,now) for p,f in universe['funds'].items() for s in f['stocks']]
    value={'schema_version':1,'session_date':str(day),'generated_utc':now.isoformat(),'feed':'iex','adjustment':'split',
           'universe_version':universe['version'],'audit_sha256':audit,'stocks':rows}
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();parse_stock(raw,now,universe)
    write(root/'local-history.json',history)
    write(root/'public-summary.json',value)
    reports=[{'symbol':s['symbol'],'parent':p,**walk_forward(history,universe,s['symbol'],p,now)} for p,f in universe['funds'].items() for s in f['stocks']]
    write(root/'walk-forward.json',{'generated_utc':now.isoformat(),'feed':'iex','reports':reports,
        'status':'BLOCKED' if all(r['completed_trades']==0 for r in reports) else 'OBSERVED'})
    # Idempotent observation: first immutable signal snapshot per session/universe.
    observation=root/'paper'/(str(day)+'-'+universe['version']+'-'+RULE_VERSION+'.json')
    if not observation.exists():write(observation,{'observed_utc':now.isoformat(),'session':str(day),'stocks':rows,'status':'PENDING_FUTURE_OUTCOMES','orders_sent':False})
    # Mature only old observations using bars strictly AFTER their observation time.
    outcomes=[]
    for path in sorted((root/'paper').glob('*.json')):
        o=json.loads(path.read_text());observed=datetime.fromisoformat(o['observed_utc'])
        for row in o['stocks']:
            forward=[b for b in history.get(row['symbol'],[]) if __import__('capital_rotation_calendar').session_close(date.fromisoformat(b['session']))>observed]
            if len(forward)>=5:
                outcomes.append({'observed_utc':o['observed_utc'],'symbol':row['symbol'],'parent':row['parent'],'state':row['state'],'rule_version':row['rule_version'],
                    'forward_5d_price_return_pct':(forward[4]['c']/forward[0]['o']-1)*100,'interpretation':'observation outcome, not filled trade'})
    write(root/'paper-outcomes.json',{'status':'OBSERVED' if outcomes else 'PENDING_FUTURE_OUTCOMES','outcomes':outcomes})
    return {'status':'COLLECTED','session':str(day),'symbols_requested':len(symbols),'stock_rows':len(rows),
            'states':{s:sum(r['state']==s for r in rows) for s in ('READY','WAIT','AVOID','BLOCKED')},'backtest_completed_trades':sum(r['completed_trades'] for r in reports),'paper_outcomes':len(outcomes),'audit_sha256':audit}

def publish(root,universe,collector_root,now):
    from rotation_publisher import load_signing_key,NoRedirect
    if os.environ.get('ALPACA_DATA_KEY_ID') or os.environ.get('ALPACA_DATA_SECRET_KEY'):raise ValueError('CREDENTIAL_CONTEXT_NOT_DISPOSED')
    v=json.loads((Path(root)/'public-summary.json').read_text());raw=json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    parse_stock(raw,now,universe)
    key=load_signing_key(Path(collector_root)/'secrets'/'rotation-staging-real-signing.dpapi')
    req=Request(ENDPOINT,data=raw,headers=stock_headers(raw,key,'windows-staging-real',now),method='POST')
    try:r=build_opener(NoRedirect()).open(req,timeout=45)
    except HTTPError as e:r=e
    response=json.loads(r.read());return {'http':r.status,'response':response,'public_bytes':len(raw)}

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['collect','publish']);p.add_argument('--root',required=True);p.add_argument('--universe',required=True);p.add_argument('--collector-root');a=p.parse_args()
    try:
        u=json.loads(Path(a.universe).read_text());now=datetime.now(timezone.utc)
        result=collect(a.root,u,now) if a.mode=='collect' else publish(a.root,u,a.collector_root,now)
        print(json.dumps(result));return 0 if result.get('http',200)==200 else 2
    except Exception:print('{"status":"BLOCKED","reason":"STOCK_COLLECTION_OR_PUBLICATION_UNAVAILABLE"}');return 2
if __name__=='__main__':raise SystemExit(main())
