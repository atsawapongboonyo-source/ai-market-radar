"""Synthetic 70-row resource/isolation probe, disposable PostgreSQL only."""
from pathlib import Path
import sys,json,gc,threading,copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

# Fingerprint only the disposable test database before/after a CI container
# restart. No live URL is accepted; no row bodies/nonces are written or logged.
if len(sys.argv) == 3 and sys.argv[1] in ('--snapshot', '--verify-snapshot'):
    import hashlib, os, time
    from urllib.parse import urlparse
    import psycopg
    url = os.environ['ROTATION_TEST_DATABASE_URL']
    parsed = urlparse(url)
    if parsed.path != '/rotation_test' or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Local disposable rotation_test required')
    for attempt in range(30):
        try:
            connection = psycopg.connect(url, connect_timeout=2)
            break
        except psycopg.OperationalError:
            if attempt == 29:
                raise
            time.sleep(1)
    fingerprint = {}
    with connection as db:
        for table in ('publications', 'stock_publications', 'nonces', 'schema_version'):
            rows = db.execute('SELECT * FROM rotation.' + table).fetchall()
            encoded = sorted(json.dumps(row, default=str) for row in rows)
            fingerprint[table] = dict(rows=len(rows), sha256=hashlib.sha256(
                json.dumps(encoded).encode()).hexdigest())
    target = Path(sys.argv[2])
    if sys.argv[1] == '--snapshot':
        target.write_text(json.dumps(fingerprint), encoding='utf-8')
    else:
        assert fingerprint == json.loads(target.read_text(encoding='utf-8')), 'Restart changed persisted rows'
    print(json.dumps(dict(simulation_only=True, disposable_restart_checkpoint=sys.argv[1],
                         rows={k:v['rows'] for k,v in fingerprint.items()}, matched=True)))
    sys.exit(0)

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
