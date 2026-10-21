"""Synthetic fixtures exercise contracts only; never published as market data."""
from datetime import datetime,timezone,timedelta
import unittest
from rotation_stock_engine import analyze, portfolio_warnings
from rotation_stock_backtest import walk_forward
from rotation_stock_protocol import parse_stock, stock_headers, verify_stock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from capital_rotation_calendar import trailing_sessions

NOW=datetime(2026,10,21,8,tzinfo=timezone.utc)

def histories():
    days=trailing_sessions(__import__('datetime').date(2026,10,20),120)
    return {s:[{'session':str(d),'o':100+i*k,'h':102+i*k,'l':98+i*k,'c':100+i*k,'v':100000} for i,d in enumerate(days)] for s,k in [('TEST',.5),('XLE',.2),('SPY',.1)]}

def universe():
    return {'version':'fixture-only','funds':{'XLE':{'as_of':'2026-10-19','known_at':'2026-10-21T07:00:00+00:00','source':'https://www.ssga.com/fixture-only','source_sha256':'a'*64,'kind':'VERIFIED_HOLDINGS','holdings_count':1,'stocks':[{'symbol':'TEST','weight_pct':1}]}}}

class EngineTests(unittest.TestCase):
    def test_aligned_split_adjusted_returns_and_unknown_portfolio(self):
        r=analyze('TEST','XLE',histories(),universe(),NOW)
        self.assertAlmostEqual(r['metrics']['return_5d_pct'],(159.5/157-1)*100,6)
        self.assertIn('PORTFOLIO_EXPOSURE_UNKNOWN',r['warnings'])
        self.assertFalse(r['trade_signal'])
    def test_missing_duplicate_future_zero_volume_fail_closed(self):
        for mutate in [lambda h:h['TEST'].pop(-3),lambda h:h['TEST'].append(h['TEST'][-1]),lambda h:h['TEST'][-1].update(session='2026-10-21'),lambda h:h['TEST'][-1].update(v=0)]:
            h=histories();mutate(h)
            self.assertEqual(analyze('TEST','XLE',h,universe(),NOW)['state'],'BLOCKED')
    def test_unverified_holdings_never_ready(self):
        u=universe();u['funds']['XLE']['kind']='THEMATIC_WATCHLIST'
        self.assertEqual(analyze('TEST','XLE',histories(),u,NOW)['state'],'BLOCKED')
    def test_unauthorized_holdings_not_used(self):
        self.assertEqual(portfolio_warnings('TEST','XLE',{'authorized':False,'positions':[{'symbol':'TEST','weight':1}]}),['PORTFOLIO_EXPOSURE_UNKNOWN'])
    def test_current_holdings_cannot_backfill_past_performance(self):
        r=walk_forward(histories(),universe(),'TEST','XLE',NOW)
        self.assertEqual(r['completed_trades'],0)
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn('NO_MATURE_POINT_IN_TIME_OBSERVATIONS',r['reason_codes'])
    def test_signature_domain_isolated(self):
        key=Ed25519PrivateKey.generate();raw=b'{}';h=stock_headers(raw,key,'test',NOW)
        self.assertEqual(verify_stock(raw,h,{'test':key.public_key().public_bytes_raw().hex()},NOW)[0],'test')
        from rotation_public_protocol import verify_signature,PublicDataError
        with self.assertRaises(PublicDataError):verify_signature(raw,h,{'test':key.public_key().public_bytes_raw().hex()},NOW)

class DecisionBoundaryTests(unittest.TestCase):
    def metrics(self):
        from rotation_stock_engine import METRIC_KEYS
        m={k:1.0 for k in METRIC_KEYS}
        m.update(close=100,sma20=99,sma50=97,sma20_prior5=98,median_iex_dollar_volume20=1000000,
          atr14=2,atr_pct=2,trigger=101,stop=95,target=120,net_reward_risk=2.5,distance_to_trigger_pct=1,relative_volume=1.3,
          etf_5d_pct=2,spy_5d_pct=1,etf_20d_pct=4,spy_20d_pct=2)
        return m
    def test_all_four_states_explain_boundaries(self):
        from rotation_stock_engine import decide
        m=self.metrics();self.assertEqual(decide(m)[0],'READY')
        m['relative_volume']=1;self.assertIn('VOLUME_CONFIRMATION_MISSING',decide(m)[1])
        m['atr_pct']=9;self.assertEqual(decide(m)[0],'AVOID')
        m['median_iex_dollar_volume20']=1;self.assertEqual(decide(m)[0],'BLOCKED')
        m['close']=float('nan');self.assertEqual(decide(m)[0],'BLOCKED')
    def test_authorized_concentration_and_no_fictional_correlation(self):
        w=portfolio_warnings('TEST','XLE',{'authorized':True,'positions':[{'symbol':'TEST','weight':.4,'parent_etf':'XLE'}]})
        self.assertIn('SINGLE_NAME_CONCENTRATION',w);self.assertIn('SECTOR_CONCENTRATION',w);self.assertIn('CORRELATION_UNKNOWN',w)
    def test_adjustment_and_corporate_action_mismatch(self):
        self.assertEqual(analyze('TEST','XLE',histories(),universe(),NOW,adjustment='raw')['state'],'BLOCKED')
        h=histories();h['TEST'][-1].update(o=1000,h=1100,l=900,c=1000)
        self.assertEqual(analyze('TEST','XLE',h,universe(),NOW)['reason_codes'],['CORPORATE_ACTION_OR_OUTLIER'])
    def test_no_future_universe_and_stale_bar(self):
        u=universe();u['funds']['XLE']['known_at']=(NOW+timedelta(days=1)).isoformat()
        self.assertEqual(analyze('TEST','XLE',histories(),u,NOW)['state'],'BLOCKED')
        self.assertEqual(analyze('TEST','XLE',histories(),universe(),NOW+timedelta(days=1))['state'],'BLOCKED')

class StockContractTests(unittest.TestCase):
    def payload(self):
        import json
        row=analyze('TEST','XLE',histories(),universe(),NOW)
        return {'schema_version':1,'session_date':'2026-10-20','generated_utc':NOW.isoformat(),'feed':'iex','adjustment':'split','universe_version':'fixture-only','audit_sha256':'a'*64,'stocks':[row]}
    def test_derived_only_strict_contract_and_recomputed_decision(self):
        import json
        from rotation_public_protocol import PublicDataError
        v=self.payload();parse_stock(json.dumps(v).encode(),NOW,universe())
        for mutate in (lambda v:v.update(account='private'),lambda v:v['stocks'][0].update(state='READY'),lambda v:v['stocks'].append(v['stocks'][0]),lambda v:v.update(stocks=[]),lambda v:v['stocks'][0]['metrics'].update(rs_spy_5d=999)):
            v=self.payload();mutate(v)
            with self.assertRaises(PublicDataError):parse_stock(json.dumps(v).encode(),NOW,universe())
    def test_signature_expiry_wrong_key_and_cross_path_rejected(self):
        import json
        from rotation_public_protocol import PublicDataError
        key=Ed25519PrivateKey.generate();raw=json.dumps(self.payload()).encode();keys={'test':key.public_key().public_bytes_raw().hex()}
        h=stock_headers(raw,key,'test',NOW)
        with self.assertRaises(PublicDataError):verify_stock(raw,h,keys,NOW+timedelta(seconds=301))
        from rotation_publisher import signed_headers
        with self.assertRaises(PublicDataError):verify_stock(raw,signed_headers(raw,key,'test',NOW),keys,NOW)
    def test_flask_fail_closed_ingress_and_mobile_details(self):
        from flask import Flask
        from unittest.mock import Mock
        from rotation_stock_web import register_stock
        import json
        key=Ed25519PrivateKey.generate();keys={'test':key.public_key().public_bytes_raw().hex()}
        app=Flask('stock-test');store=Mock();store.latest.return_value=None
        register_stock(app,store,keys,universe(),lambda:NOW)
        c=app.test_client();self.assertEqual(c.get('/api/rotation/stocks').get_json()['status'],'BLOCKED')
        raw=json.dumps(self.payload()).encode();h=stock_headers(raw,key,'test',NOW)
        self.assertEqual(c.post('/api/rotation/stocks/ingest',data=raw,headers=h).status_code,400)
        store.publish.return_value=('ACCEPTED',200)
        self.assertEqual(c.post('/api/rotation/stocks/ingest',data=raw,headers={**h,'X-Forwarded-Proto':'https'}).status_code,200)
        self.assertEqual(c.get('/api/rotation/stocks').headers['Cache-Control'],'no-store')

class HistoricalCollectorTests(unittest.TestCase):
    def test_only_readonly_iex_split_url_and_no_future_bar(self):
        from rotation_stock_collector import fetch_history
        from contextlib import contextmanager
        import json
        seen=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({'bars':{'TEST':[{'t':'2026-10-20T04:00:00Z','o':1,'h':2,'l':1,'c':2,'v':100}]}}).encode()
        def opener(req,timeout):seen.append(req);return Response()
        fetch_history({'TEST'},__import__('datetime').date(2026,10,20),'unit-key','unit-secret',opener)
        self.assertTrue(all(r.full_url.startswith('https://data.alpaca.markets/v2/stocks/bars?') and 'feed=iex' in r.full_url and 'adjustment=split' in r.full_url and r.method=='GET' for r in seen))
    def test_walk_forward_never_passes_future_bars_to_engine(self):
        from unittest.mock import patch
        h=histories();u=universe();u['funds']['XLE'].update(known_at='2026-04-01T00:00:00+00:00',as_of='2026-04-01')
        checked=[]
        def inspect(symbol,parent,history,universe,now):
            from capital_rotation_calendar import last_completed_session
            self.assertTrue(all(r['session']<=str(last_completed_session(now)) for rows in history.values() for r in rows));checked.append(now)
            return {'state':'WAIT'}
        with patch('rotation_stock_backtest.analyze',side_effect=inspect):walk_forward(h,u,'TEST','XLE',NOW)
        self.assertGreater(len(checked),0)
    def test_walk_forward_costs_stop_first_and_benchmark(self):
        from unittest.mock import patch
        h=histories();u=universe();u['funds']['XLE'].update(known_at='2026-04-01T00:00:00+00:00',as_of='2026-04-01')
        for r in h['TEST']:r.update(o=100,h=125,l=90,c=105,v=100000)
        with patch('rotation_stock_backtest.analyze',return_value={'state':'READY','metrics':{'trigger':101,'stop':95,'target':120}}):r=walk_forward(h,u,'TEST','XLE',NOW)
        self.assertGreater(r['completed_trades'],0)
        self.assertEqual(r['trades'][0]['exit_reason'],'STOP_FIRST')
        self.assertLess(r['trades'][0]['net_return_pct'],(95/101-1)*100)
        self.assertGreater(r['mark_to_market_max_drawdown_pct'],0)
        self.assertGreater(r['false_positives'],0)
        self.assertIn('spy_return_pct',r['trades'][0])
