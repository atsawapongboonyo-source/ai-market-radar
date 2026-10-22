"""Offline real-scanner isolation/RAM probe. No market-data network calls."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psutil
import scanner
import legacy_scanner
from rotation_web import RotationSite
from werkzeug.test import Client
from werkzeug.wrappers import Response
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rotation_publisher import signed_headers
from test_rotation_web import fake_public

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
process=psutil.Process()
gc.collect()
before=process.memory_info().rss
threads_before=threading.active_count()
functions=dict(scanner.app.view_functions)
positions=[{'ticker':'TEST','avg_cost':100,'price':price,'shares':10,'buy_low':98,'buy_high':102,'stop':95,'tp1':110,'tp2':120} for price in (94,105,115)]
position_before=[legacy_scanner._position_manage(p) for p in positions]
with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
    for target in ('yfinance.download','yfinance.Ticker'):
        stack.enter_context(patch(target,side_effect=AssertionError('NO_MARKET_DOWNLOADS_ALLOWED')))
    now=datetime.now(timezone.utc)
    key=Ed25519PrivateKey.generate()
    site=RotationSite(scanner.app,database=str(Path(directory)/'public.sqlite'),
        public_keys={'probe':key.public_key().public_bytes_raw().hex()},
        loopback_staging=True,simulated=True,clock=lambda:now)
    client=Client(site,Response)
    raw=json.dumps(fake_public(now)).encode()
    response=client.post('/api/rotation/ingest',data=raw,headers=signed_headers(raw,key,'probe',now),environ_overrides={'REMOTE_ADDR':'127.0.0.1'})
    assert response.status_code==200,response.data
    for _ in range(1500):
        assert client.get('/api/rotation').status_code==200
    rotation=client.get('/rotation')
    home=client.get('/')
    assert b'v531LiveRotation' not in rotation.data
    assert b'capital-rotation-nav' in home.data
    assert scanner.app.view_functions==functions
    assert position_before==[legacy_scanner._position_manage(p) for p in positions]
    assert threads_before==threading.active_count()
    gc.collect()
    after=process.memory_info().rss
    result={'runtime_version':scanner.RUNTIME_VERSION,'scanner_view_functions_unchanged':True,
        'position_engine_result_unchanged':True,'rotation_has_no_scanner_injections':True,
        'market_downloads':0,'background_threads_added':0,'requests':1500,
        'rss_before_mib':round(before/2**20,3),'rss_after_mib':round(after/2**20,3),
        'rss_delta_mib':round((after-before)/2**20,3),'ingest_status':response.status_code}
    assert after-before < 32*2**20,result
args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
