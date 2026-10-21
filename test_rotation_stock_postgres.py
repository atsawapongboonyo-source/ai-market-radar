"""Disposable PostgreSQL only: stock writes must preserve baseline and nonce semantics."""
import os,json,unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from rotation_store import PublicStore
from rotation_stock_store import StockStore
from rotation_stock_web import register_stock
from rotation_stock_protocol import stock_headers
from test_rotation_stock import NOW,universe,histories
import test_rotation_stock as fixture
from test_rotation_web import fake_public
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask

@unittest.skipUnless(os.environ.get('ROTATION_TEST_DATABASE_URL'),'disposable PostgreSQL not configured')
class StockPostgresTests(unittest.TestCase):
    def setUp(self):
        self.url=os.environ['ROTATION_TEST_DATABASE_URL']
        if urlparse(self.url).path!='/rotation_test':raise RuntimeError('Disposable rotation_test required')
        self.base=PublicStore(self.url);self.base.migrate();self.store=StockStore(self.url);self.store.migrate()
        with self.base.connect(write=True) as db:
            db.execute('TRUNCATE rotation.publications,rotation.nonces,rotation.stock_publications')
            db.execute('UPDATE rotation.schema_version SET signature_not_before=0')
        self.value=fixture.StockContractTests().payload();self.raw=json.dumps(self.value).encode()
        baseline=fake_public(NOW);m=self.value['stocks'][0]['metrics']
        for w in (5,20):baseline['returns'][f'{w}d'].update(SPY=m[f'spy_{w}d_pct'],XLE=m[f'etf_{w}d_pct'])
        self.baseline=json.dumps(baseline).encode();self.base.publish(self.baseline,baseline,'base','f'*32,NOW)
        self.key=Ed25519PrivateKey.generate();self.app=self.new_app()
    def new_app(self):
        app=Flask('stock');register_stock(app,self.store,{'test':self.key.public_key().public_bytes_raw().hex()},universe(),lambda:NOW);return app
    def post(self,h=None,raw=None,app=None):
        raw=raw or self.raw;h=h or stock_headers(raw,self.key,'test',NOW)
        return (app or self.app).test_client().post('/api/rotation/stocks/ingest',data=raw,headers={**h,'X-Forwarded-Proto':'https'})
    def test_restart_and_baseline_unchanged(self):
        h=stock_headers(self.raw,self.key,'test',NOW)
        self.assertEqual(self.post(h).status_code,200)
        self.assertEqual(self.post(h,app=self.new_app()).status_code,409)
        self.assertEqual(StockStore(self.url).latest(),self.raw)
        self.assertEqual(self.base.latest(),self.baseline)
    def test_concurrent_replay_and_duplicate_session(self):
        h=stock_headers(self.raw,self.key,'test',NOW)
        with ThreadPoolExecutor(8) as p:codes=list(p.map(lambda _:self.post(h).status_code,range(16)))
        self.assertEqual(codes.count(200),1);self.assertEqual(codes.count(409),15)
        self.assertEqual(self.post().get_json()['status'],'UNCHANGED')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM rotation.stock_publications').fetchone()[0],1)
    def test_shared_nonce_domain_rejects_cross_endpoint_reuse(self):
        h=stock_headers(self.raw,self.key,'base',NOW,nonce='f'*32)
        # Storage reuse is denied even with a valid signature in the stock domain.
        self.assertEqual(self.store.publish(self.raw,self.value,'base','f'*32,NOW,signed_timestamp=int(NOW.timestamp()))[0],'REPLAY_REJECTED')
    def test_mismatched_baseline_rejected(self):
        v=json.loads(self.raw);v['stocks'][0]['metrics']['etf_5d_pct']+=1
        self.assertEqual(self.store.publish(json.dumps(v).encode(),v,'test','c'*32,NOW,signed_timestamp=int(NOW.timestamp()))[0],'BASELINE_MISMATCH')
        self.assertEqual(self.base.latest(),self.baseline)
    def test_failed_insert_rolls_back_nonce(self):
        with self.store.connect() as db:
            db.execute("CREATE OR REPLACE FUNCTION rotation.stock_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test failure'; END $$")
            db.execute('CREATE TRIGGER stock_test_fail BEFORE INSERT ON rotation.stock_publications FOR EACH ROW EXECUTE FUNCTION rotation.stock_test_fail()')
        try:
            self.assertEqual(self.post().status_code,503)
            with self.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM rotation.nonces WHERE key_id='test'").fetchone()[0],0)
        finally:
            with self.store.connect() as db:
                db.execute('DROP TRIGGER stock_test_fail ON rotation.stock_publications');db.execute('DROP FUNCTION rotation.stock_test_fail()')
