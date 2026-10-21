"""Synthetic 70-row resource/isolation probe, disposable PostgreSQL only."""
from pathlib import Path
import sys,json,gc,threading,copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psutil
from unittest.mock import patch
from test_rotation_stock_postgres import StockPostgresTests
from test_rotation_stock import NOW,universe
from rotation_stock_protocol import stock_headers
from rotation_stock_web import register_stock
from rotation_web import RotationSite
import scanner
from werkzeug.test import Client
from werkzeug.wrappers import Response
case=StockPostgresTests();case.setUp()
u=universe();u['funds']['XLE']['stocks']=[{'symbol':f'T{i:03}','weight_pct':1} for i in range(70)];u['funds']['XLE']['holdings_count']=70
v=copy.deepcopy(case.value);template=v['stocks'][0];v['stocks']=[{**template,'symbol':s['symbol']} for s in u['funds']['XLE']['stocks']]
raw=json.dumps(v).encode();site=RotationSite(scanner.app,database=case.url,public_keys={'test':case.key.public_key().public_bytes_raw().hex()},clock=lambda:NOW,simulated=True)
current=register_stock(site.rotation_app,case.store,{'test':case.key.public_key().public_bytes_raw().hex()},u,lambda:NOW)
from rotation_opportunities import install_opportunities
install_opportunities(scanner.app,site.rotation_app,current,lambda:NOW)
client=Client(site,Response);headers={**stock_headers(raw,case.key,'test',NOW),'X-Forwarded-Proto':'https'}
assert client.post('/api/rotation/stocks/ingest',data=raw,headers=headers).status_code==200
functions=dict(scanner.app.view_functions);baseline=case.base.latest();stock_before=case.store.latest();threads=threading.active_count();proc=psutil.Process();gc.collect();before=proc.memory_info().rss
with patch('yfinance.download',side_effect=AssertionError('No market download')),patch('yfinance.Ticker',side_effect=AssertionError('No market download')):
    for _ in range(500):
        response=client.get('/api/rotation/stocks');assert response.status_code==200 and len(response.json['stocks'])==70
        response=client.get('/api/rotation/opportunities');assert len(response.json['cards'])==70
    assert client.get('/rotation').status_code==200
assert case.base.latest()==baseline and scanner.app.view_functions==functions and threading.active_count()==threads
assert case.store.latest()==stock_before  # Home/API reads cannot change persistent signed data.
gc.collect();after=proc.memory_info().rss;assert after-before<64*2**20
with case.store.connect() as db:size=db.execute("SELECT pg_total_relation_size('rotation.stock_publications')").fetchone()[0]
print(json.dumps({'simulation_only':True,'stock_rows':70,'requests':500,'payload_bytes':len(raw),'rss_delta_mib':round((after-before)/2**20,3),'stock_relation_bytes':size,'baseline_unchanged':True,'scanner_functions_unchanged':True,'market_downloads':0,'background_threads_added':0}))
