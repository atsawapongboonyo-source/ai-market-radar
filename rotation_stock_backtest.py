"""Frozen-rule chronological evaluation. Never claim current holdings are historic.
Trade simulation: next-session stop entry, adverse gap fills, stop-first ambiguous
bars, exit after <=5 sessions, 40 bps per side, $1000 research notional, <=1% IEX
activity. Results describe partial-feed price returns, not executable quotes.
"""
from datetime import datetime,timedelta,timezone
from math import sqrt
from rotation_stock_engine import analyze,COST_BPS_PER_SIDE
from capital_rotation_calendar import ny_timezone,session_close

def walk_forward(histories,universe,symbol,parent,now):
    histories={s:[r for r in h if session_close(__import__('datetime').date.fromisoformat(r['session']))<=now] for s,h in histories.items()}
    rows=histories.get(symbol,[]);trades=[];eligible=0;pending=0;last_exit=-1
    fund=universe.get('funds',{}).get(parent)
    if not fund:return {'status':'BLOCKED','reason_codes':['NO_POINT_IN_TIME_UNIVERSE'],'completed_trades':0,'trades':[]}
    known=datetime.fromisoformat(fund['known_at'])
    for i in range(59,len(rows)-1):
        # Membership must actually be available at the decision timestamp.
        close=session_close(__import__('datetime').date.fromisoformat(rows[i]['session']))+timedelta(minutes=20)
        if known>close or close>now:continue
        eligible+=1
        sliced={s:[r for r in h if r['session']<=rows[i]['session']] for s,h in histories.items()}
        signal=analyze(symbol,parent,sliced,universe,close)
        if signal['state']!='READY' or i<=last_exit:continue
        future=rows[i+1:i+6]
        if len(future)<5:pending+=1;continue
        m=signal['metrics'];entry=None;entry_index=None;exit_price=None;exit_index=None;reason=None
        for j,bar in enumerate(future,i+1):
            if entry is None:
                if bar['h']<m['trigger']:continue
                entry=max(bar['o'],m['trigger']);entry_index=j
                gap_cost=(entry+m['target'])*COST_BPS_PER_SIDE/10000
                if entry<=m['stop'] or m['target']<=entry or (m['target']-entry-gap_cost)/(entry-m['stop']+gap_cost)<2 or 1000>bar['c']*bar['v']*.01:entry=None;break
            if bar['o']<=m['stop']:exit_price=bar['o'];reason='GAP_STOP'
            elif bar['l']<=m['stop']:exit_price=m['stop'];reason='STOP_FIRST'
            elif bar['h']>=m['target']:exit_price=max(bar['o'],m['target']);reason='TARGET'
            if exit_price is not None:exit_index=j;break
        if entry is None:continue
        if exit_price is None:exit_price=future[-1]['c'];exit_index=i+5;reason='TIME_EXIT'
        last_exit=exit_index
        net=(exit_price*(1-COST_BPS_PER_SIDE/10000)/(entry*(1+COST_BPS_PER_SIDE/10000))-1)*100
        spy=histories['SPY'];spy_by={r['session']:r for r in spy}
        benchmark=(spy_by[rows[exit_index]['session']]['c']/spy_by[rows[entry_index]['session']]['o']-1)*100
        trades.append({'signal_session':rows[i]['session'],'entry_session':rows[entry_index]['session'],'exit_session':rows[exit_index]['session'],
                       'mark_to_market_path_pct':[(rows[k]['c']*(1-COST_BPS_PER_SIDE/10000)/(entry*(1+COST_BPS_PER_SIDE/10000))-1)*100 for k in range(entry_index,exit_index)]+[net],
                       'net_return_pct':round(net,6),'spy_return_pct':round(benchmark,6),'exit_reason':reason})
    equity=1.;peak=1.;drawdown=0.;mtm_peak=1.;mtm_drawdown=0.
    for t in trades:
        for r in t['mark_to_market_path_pct']:
            marked=equity*(1+r/100);mtm_peak=max(mtm_peak,marked);mtm_drawdown=max(mtm_drawdown,(mtm_peak-marked)/mtm_peak*100)
        equity*=1+t['net_return_pct']/100;peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak*100)
    return {'status':'OBSERVED' if trades else 'BLOCKED','reason_codes':[] if trades else ['NO_MATURE_POINT_IN_TIME_OBSERVATIONS'],
            'completed_trades':len(trades),'eligible_decisions':eligible,'pending':pending,'trades':trades,
            'false_positives':sum(t['net_return_pct']<=0 for t in trades),'closed_trade_max_drawdown_pct':round(drawdown,6) if trades else None,'mark_to_market_max_drawdown_pct':round(mtm_drawdown,6) if trades else None,
            'trade_frequency_per_eligible_session':len(trades)/eligible if eligible else None,
            'net_compounded_return_pct':round((equity-1)*100,6) if trades else None,
            'warning':'No point-in-time historical archive means no retrospective performance claim; no parameter fitting.'}
