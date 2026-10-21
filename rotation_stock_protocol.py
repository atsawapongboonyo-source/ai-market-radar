"""Strict derived-only stock contract with separate Ed25519 signature domain."""
from datetime import datetime
import hashlib,json,re,secrets
from rotation_public_protocol import PublicDataError
from rotation_stock_engine import decide,RULE_VERSION,METRIC_KEYS
from capital_rotation_calendar import last_completed_session
STOCK_PATH='/api/rotation/stocks/ingest'
MAX_STOCK_BODY=131072
BLOCK_REASONS={'UNVERIFIED_MEMBERSHIP','STALE_OR_FUTURE_UNIVERSE','INCOMPARABLE_ADJUSTMENT','DUPLICATE_OR_FUTURE_BAR','MISALIGNED_OR_MISSING_BARS','INVALID_OHLCV','INCONSISTENT_OHLC','INVALID_RISK_REFERENCES','MISSING_OR_UNSUPPORTED_DATA','LOW_IEX_LIQUIDITY','CORPORATE_ACTION_OR_OUTLIER'}
WARNINGS={'PORTFOLIO_EXPOSURE_UNKNOWN','SINGLE_NAME_CONCENTRATION','SECTOR_CONCENTRATION','SECTOR_EXPOSURE_UNKNOWN','CORRELATION_UNKNOWN','HIGH_HISTORICAL_CORRELATION','NO_THRESHOLD_WARNING_FROM_PROVIDED_SNAPSHOT'}

def message(raw,timestamp,nonce,key_id):
    return ('rotation-stock-v1\nPOST\n'+STOCK_PATH+'\n'+key_id+'\n'+timestamp+'\n'+nonce+'\n'+hashlib.sha256(raw).hexdigest()).encode('ascii')

def stock_headers(raw,key,key_id,now,nonce=None):
    ts=str(int(now.timestamp()));nonce=nonce or secrets.token_hex(16)
    return {'Content-Type':'application/json','X-Rotation-Key-Id':key_id,'X-Rotation-Timestamp':ts,'X-Rotation-Nonce':nonce,'X-Rotation-Signature':key.sign(message(raw,ts,nonce,key_id)).hex()}

def verify_stock(raw,headers,keys,now):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        kid=headers.get('X-Rotation-Key-Id','');ts=headers.get('X-Rotation-Timestamp','');nonce=headers.get('X-Rotation-Nonce','');sig=headers.get('X-Rotation-Signature','')
        if kid not in keys or not re.fullmatch('[0-9]{10}',ts) or abs(now.timestamp()-int(ts))>300 or not re.fullmatch('[a-f0-9]{32}',nonce) or not re.fullmatch('[a-f0-9]{128}',sig):raise ValueError()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys[kid])).verify(bytes.fromhex(sig),message(raw,ts,nonce,kid))
        return kid,nonce
    except (ValueError,TypeError,InvalidSignature):raise PublicDataError('INVALID_SIGNATURE') from None

def parse_stock(raw,now,universe):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise PublicDataError('INVALID_STOCK_SCHEMA')
            d[k]=v
        return d
    try:
        if len(raw)>MAX_STOCK_BODY:raise ValueError()
        v=json.loads(raw,object_pairs_hook=unique)
        if set(v)!={'schema_version','session_date','generated_utc','feed','adjustment','universe_version','audit_sha256','stocks'} or type(v['schema_version']) is not int or v['schema_version']!=1:raise ValueError()
        if v['feed']!='iex' or v['adjustment']!='split' or v['universe_version']!=universe['version'] or not re.fullmatch('[a-f0-9]{64}',v['audit_sha256']):raise ValueError()
        if v['session_date']!=str(last_completed_session(now)):raise PublicDataError('STALE_SESSION')
        generated=datetime.fromisoformat(v['generated_utc'])
        if generated.tzinfo is None or not -60<=(now-generated).total_seconds()<=36*3600:raise PublicDataError('STALE_PUBLICATION')
        if type(v['stocks']) is not list or not 1<=len(v['stocks'])<=70:raise ValueError()
        expected={(p,s['symbol']) for p,f in universe['funds'].items() for s in f['stocks']}
        seen=set()
        for row in v['stocks']:
            if set(row)!={'parent','symbol','metrics','state','reason_codes','warnings','trade_signal','rule_version'} or row['trade_signal'] is not False or row['rule_version']!=RULE_VERSION:raise ValueError()
            pair=(row['parent'],row['symbol'])
            if pair in seen or pair not in expected:raise ValueError()
            seen.add(pair)
            fund=universe['funds'][row['parent']]
            if fund['kind']!='VERIFIED_HOLDINGS' or datetime.fromisoformat(fund['known_at'])>generated or fund['as_of']>v['session_date']:raise ValueError()
            if (now-datetime.fromisoformat(fund['known_at'])).total_seconds()>7*86400 or (__import__('datetime').date.fromisoformat(v['session_date'])-__import__('datetime').date.fromisoformat(fund['as_of'])).days>7:raise PublicDataError('STALE_UNIVERSE')
            if type(row['warnings']) is not list or not set(row['warnings'])<=WARNINGS or not row['warnings']:raise ValueError()
            if row['metrics'] is None:
                if row['state']!='BLOCKED' or not row['reason_codes'] or not set(row['reason_codes'])<=BLOCK_REASONS:raise ValueError()
            else:
                m=row['metrics'];state,reasons=decide(m,row['parent'])
                if (state,reasons)!=(row['state'],row['reason_codes']):raise ValueError()
                if not (m['close']>0 and m['trigger']>m['stop']>0 and m['atr14']>0):raise ValueError()
                costs=(m['trigger']+max(m['target'],m['trigger']))*.004
                if abs(m['net_reward_risk']-(m['target']-m['trigger']-costs)/(m['trigger']-m['stop']+costs))>1e-6:raise ValueError()
                if abs(m['atr_pct']-m['atr14']/m['close']*100)>1e-6 or abs(m['distance_to_trigger_pct']-(m['trigger']/m['close']-1)*100)>1e-6:raise ValueError()
                for w in (5,20):
                    if abs(m[f'rs_spy_{w}d']-(m[f'return_{w}d_pct']-m[f'spy_{w}d_pct']))>1e-5 or abs(m[f'rs_etf_{w}d']-(m[f'return_{w}d_pct']-m[f'etf_{w}d_pct']))>1e-5:raise ValueError()
        if seen!=expected:raise PublicDataError('INCOMPLETE_STOCK_COVERAGE')
        return v
    except PublicDataError:raise
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):raise PublicDataError('INVALID_STOCK_SCHEMA') from None
