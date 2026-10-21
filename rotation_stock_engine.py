"""Deterministic EOD research gates. Price returns exclude dividends.
IEX dollar volume is partial-market activity, never consolidated liquidity.
"""
from datetime import date,datetime,timedelta,timezone
from statistics import mean,median,correlation
from math import isfinite
from capital_rotation_calendar import trailing_sessions,last_completed_session

RULE_VERSION='eod-v1.1'
COST_BPS_PER_SIDE=40
METRIC_KEYS={'close','return_5d_pct','return_20d_pct','spy_5d_pct','spy_20d_pct','etf_5d_pct','etf_20d_pct','rs_spy_5d','rs_spy_20d','rs_etf_5d','rs_etf_20d','sma20','sma50','sma20_prior5','atr14','atr_pct','median_iex_dollar_volume20','relative_volume','trigger','stop','target','net_reward_risk','distance_to_trigger_pct'}

def portfolio_warnings(symbol,parent,portfolio=None,*,now=None):
    if not portfolio or portfolio.get('authorized') is not True:
        return ['PORTFOLIO_EXPOSURE_UNKNOWN']
    try:
        now=now or datetime.now(timezone.utc)
        asof=datetime.fromisoformat(portfolio['as_of'])
        assert asof.tzinfo is not None and 0<=(now-asof).total_seconds()<=24*3600
        assert portfolio.get('source') in ('manual_user_snapshot','authorized_readonly_connector')
        positions=portfolio['positions']
        assert positions and len(positions)<=100 and all(type(p['weight']) in (int,float) and isfinite(p['weight']) and 0<=p['weight']<=1 for p in positions)
        assert sum(p['weight'] for p in positions)<=1.000001
        warnings=[]
        if sum(p['weight'] for p in positions if p['symbol']==symbol)>=.1:warnings.append('SINGLE_NAME_CONCENTRATION')
        if any('parent_etf' not in p for p in positions):warnings.append('SECTOR_EXPOSURE_UNKNOWN')
        elif sum(p['weight'] for p in positions if p['parent_etf']==parent)>=.3:warnings.append('SECTOR_CONCENTRATION')
        candidate=portfolio.get('candidate_returns')
        sessions=portfolio.get('candidate_return_sessions',[])
        if candidate and len(sessions)==len(candidate)>=20 and sessions==sorted(set(sessions)) and all(p.get('aligned_returns') and p.get('return_sessions')==sessions for p in positions):
            for p in positions:
                if p['weight']>0 and len(candidate)==len(p['aligned_returns'])>=20 and correlation(candidate,p['aligned_returns'])>=.8:
                    warnings.append('HIGH_HISTORICAL_CORRELATION');break
        else:warnings.append('CORRELATION_UNKNOWN')
        return warnings or ['NO_THRESHOLD_WARNING_FROM_PROVIDED_SNAPSHOT']
    except (KeyError,TypeError,ValueError,AssertionError):return ['PORTFOLIO_EXPOSURE_UNKNOWN']

def decide(m,parent=None):
    if set(m)!=METRIC_KEYS or any(type(v) not in (int,float) or not isfinite(v) for v in m.values()):
        return 'BLOCKED',['INVALID_METRICS']
    if m['median_iex_dollar_volume20']<300000:return 'BLOCKED',['LOW_IEX_LIQUIDITY']
    if m['close']<5:return 'AVOID',['LOW_PRICE']
    risk=[];wait=[]
    if m['atr_pct']>8:risk.append('EXCESS_VOLATILITY')
    if m['close']<m['sma50']:risk.append('BELOW_LONG_TREND')
    if m['close']>m['trigger']+2*m['atr14']:risk.append('OVEREXTENDED')
    if risk:return 'AVOID',risk
    sector_leads=(min(m['spy_5d_pct'],m['spy_20d_pct'])>0) if parent=='SPY' else (m['etf_5d_pct']>m['spy_5d_pct'] and m['etf_20d_pct']>m['spy_20d_pct'])
    if not sector_leads:wait.append('SECTOR_NOT_LEADING')
    if min(m[k] for k in ('rs_spy_5d','rs_spy_20d','rs_etf_5d','rs_etf_20d'))<=0:wait.append('RELATIVE_STRENGTH_INCOMPLETE')
    if not (m['close']>m['sma20']>m['sma50'] and m['sma20']>m['sma20_prior5']):wait.append('TREND_UNCONFIRMED')
    if not -1<=m['distance_to_trigger_pct']<=2:wait.append('OUTSIDE_TRIGGER_ZONE')
    if m['relative_volume']<1.2:wait.append('VOLUME_CONFIRMATION_MISSING')
    if m['target']<=m['trigger']:wait.append('NO_OBSERVED_RESISTANCE_TARGET')
    elif m['net_reward_risk']<2:wait.append('NET_REWARD_RISK_BELOW_2')
    return ('WAIT',wait) if wait else ('READY',['ALL_RESEARCH_GATES_PASSED'])

def analyze(symbol,parent,histories,universe,now,*,adjustment='split',portfolio=None):
    result={'symbol':symbol,'parent':parent,'state':'BLOCKED','reason_codes':[],
        'warnings':portfolio_warnings(symbol,parent,portfolio,now=now),'metrics':None,
        'trade_signal':False,'rule_version':RULE_VERSION}
    try:
        day=last_completed_session(now)
        fund=universe['funds'][parent]
        known=datetime.fromisoformat(fund['known_at'])
        asof=date.fromisoformat(fund['as_of'])
        if fund['kind']!='VERIFIED_HOLDINGS' or symbol not in [r['symbol'] for r in fund['stocks']]:raise ValueError('UNVERIFIED_MEMBERSHIP')
        if known.tzinfo is None or known>now or (now-known).total_seconds()>7*86400 or asof>day or (day-asof).days>7:raise ValueError('STALE_OR_FUTURE_UNIVERSE')
        if adjustment!='split':raise ValueError('INCOMPARABLE_ADJUSTMENT')
        required=[str(d) for d in trailing_sessions(day,60)]
        series={}
        for s in (symbol,parent,'SPY'):
            rows=histories[s]
            dates=[r['session'] for r in rows]
            if len(dates)!=len(set(dates)) or dates!=sorted(dates) or any(d>str(day) for d in dates):raise ValueError('DUPLICATE_OR_FUTURE_BAR')
            rows=rows[-60:]
            if [r['session'] for r in rows]!=required:raise ValueError('MISALIGNED_OR_MISSING_BARS')
            for r in rows:
                if any(type(r[k]) not in (int,float) or not isfinite(r[k]) or r[k]<=0 for k in ('o','h','l','c','v')):raise ValueError('INVALID_OHLCV')
                if not r['l']<=min(r['o'],r['c'])<=max(r['o'],r['c'])<=r['h']:raise ValueError('INCONSISTENT_OHLC')
            if any(abs(rows[i]['c']/rows[i-1]['c']-1)>.5 for i in range(1,len(rows))):raise ValueError('CORPORATE_ACTION_OR_OUTLIER')
            series[s]=rows
        rows=series[symbol];c=[r['c'] for r in rows]
        returns=lambda s,n:(series[s][-1]['c']/series[s][-1-n]['c']-1)*100
        atr=mean(max(rows[i]['h']-rows[i]['l'],abs(rows[i]['h']-rows[i-1]['c']),abs(rows[i]['l']-rows[i-1]['c'])) for i in range(46,60))
        trigger=max(r['h'] for r in rows[-21:-1])+atr*.1
        stop=max(min(r['l'] for r in rows[-10:]),trigger-2*atr)
        target=max(r['h'] for r in rows[:-1])
        costs=(trigger+max(target,trigger))*COST_BPS_PER_SIDE/10000
        if trigger<=stop or atr<=0:raise ValueError('INVALID_RISK_REFERENCES')
        m={'close':c[-1],'return_5d_pct':returns(symbol,5),'return_20d_pct':returns(symbol,20),
           'spy_5d_pct':returns('SPY',5),'spy_20d_pct':returns('SPY',20),
           'etf_5d_pct':returns(parent,5),'etf_20d_pct':returns(parent,20),
           'sma20':mean(c[-20:]),'sma50':mean(c[-50:]),'sma20_prior5':mean(c[-25:-5]),
           'atr14':atr,'atr_pct':atr/c[-1]*100,'median_iex_dollar_volume20':median(r['c']*r['v'] for r in rows[-20:]),
           'relative_volume':rows[-1]['v']/median(r['v'] for r in rows[-21:-1]),
           'trigger':trigger,'stop':stop,'target':target,
           'net_reward_risk':(target-trigger-costs)/(trigger-stop+costs),
           'distance_to_trigger_pct':(trigger/c[-1]-1)*100}
        for w in (5,20):
            m[f'rs_spy_{w}d']=m[f'return_{w}d_pct']-m[f'spy_{w}d_pct']
            m[f'rs_etf_{w}d']=m[f'return_{w}d_pct']-m[f'etf_{w}d_pct']
        m={k:round(v,8) for k,v in m.items()}
        state,reasons=decide(m,parent)
        result.update(metrics=m,state=state,reason_codes=reasons)
    except (KeyError,ValueError,TypeError,IndexError,ZeroDivisionError) as exc:
        safe={'UNVERIFIED_MEMBERSHIP','STALE_OR_FUTURE_UNIVERSE','INCOMPARABLE_ADJUSTMENT','DUPLICATE_OR_FUTURE_BAR','MISALIGNED_OR_MISSING_BARS','INVALID_OHLCV','INCONSISTENT_OHLC','INVALID_RISK_REFERENCES','CORPORATE_ACTION_OR_OUTLIER'}
        result['reason_codes']=[str(exc) if str(exc) in safe else 'MISSING_OR_UNSUPPORTED_DATA']
    return result
