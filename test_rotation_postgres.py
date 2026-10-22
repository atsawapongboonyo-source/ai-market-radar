"""Real PostgreSQL tests, strictly restricted to a disposable rotation_test DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask
from rotation_backup import restore_drill
from rotation_publisher import signed_headers
from rotation_public_protocol import INGEST_PATH
from rotation_store import PublicStore, StoreUnavailable
from rotation_web import register_rotation
from test_rotation_web import fake_public


@unittest.skipUnless(os.environ.get('ROTATION_TEST_DATABASE_URL'), 'disposable PostgreSQL not configured')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ['ROTATION_TEST_DATABASE_URL']
        if urlparse(self.url).path != '/rotation_test':
            raise RuntimeError('Tests require a disposable rotation_test database')
        self.store = PublicStore(self.url)
        self.store.migrate()
        with self.store.connect(write=True) as db:
            db.execute('TRUNCATE rotation.publications, rotation.nonces')
            db.execute('UPDATE rotation.schema_version SET signature_not_before=0')
        self.now = datetime(2026,10,21,12,tzinfo=timezone.utc)
        self.key = Ed25519PrivateKey.generate()
        self.app = self.new_app()
        self.raw = json.dumps(fake_public(self.now)).encode()

    def new_app(self):
        app = Flask(__name__)
        register_rotation(app,database=self.url,
            public_keys={'test': self.key.public_key().public_bytes_raw().hex()},
            clock=lambda: self.now,loopback_staging=True)
        return app

    def post(self, raw=None, headers=None, app=None):
        raw = self.raw if raw is None else raw
        with (app or self.app).test_client() as client:
            return client.post(INGEST_PATH,data=raw,
                headers=headers or signed_headers(raw,self.key,'test',self.now))

    def counts(self):
        with self.store.connect() as db:
            return tuple(db.execute(f'SELECT count(*) FROM rotation.{t}').fetchone()[0] for t in ('publications','nonces'))

    def test_concurrent_identical_request_one_accept_rest_replay(self):
        headers = signed_headers(self.raw,self.key,'test',self.now)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: self.post(headers=headers).status_code, range(24)))
        self.assertEqual(results.count(200),1)
        self.assertEqual(results.count(409),23)
        self.assertEqual(self.counts(),(1,1))

    def test_duplicate_sessions_with_distinct_nonces(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: self.post().get_json()['status'],range(24)))
        self.assertEqual(results.count('ACCEPTED'),1)
        self.assertEqual(results.count('UNCHANGED'),23)
        self.assertEqual(self.counts(),(1,24))

    def test_concurrent_updates_cannot_roll_back_latest(self):
        raws=[]
        for i in range(20):
            value=fake_public(self.now)
            value['generated_utc']=(self.now-timedelta(seconds=i)).isoformat()
            raws.append(json.dumps(value).encode())
        with ThreadPoolExecutor(max_workers=10) as pool:
            results=list(pool.map(lambda raw: self.post(raw).status_code,raws))
        self.assertTrue(all(r in (200,409) for r in results))
        self.assertEqual(json.loads(self.store.latest())['generated_utc'], self.now.isoformat())
        self.assertEqual(self.counts(),(1,20))

    def test_restart_replay_and_publication_persist(self):
        headers=signed_headers(self.raw,self.key,'test',self.now)
        self.assertEqual(self.post(headers=headers).status_code,200)
        self.assertEqual(self.post(headers=headers,app=self.new_app()).get_json()['error_code'],'REPLAY_REJECTED')
        self.store.migrate()
        self.assertEqual(PublicStore(self.url).latest(),self.raw)
        self.assertEqual(self.counts(),(1,1))

    def test_transaction_failure_rolls_back_nonce_and_publication(self):
        original=self.store.execute
        def fail(store,db,sql,params=()):
            if sql.startswith('INSERT INTO rotation.publications'):
                raise RuntimeError('simulated DB failure')
            return original(db,sql,params)
        with patch.object(PublicStore,'execute',fail):
            response=self.post()
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.get_json()['error_code'],'STORE_UNAVAILABLE')
        self.assertEqual(self.counts(),(0,0))
        self.assertEqual(self.post().status_code,200)

    def test_restore_drill_preserves_live_tables(self):
        self.post()
        before=self.counts()
        result=restore_drill(self.store)
        self.assertEqual(result['status'],'VERIFIED')
        self.assertFalse(result['source_modified'])
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.store.latest(),self.raw)

    def test_schema_constraints_and_expiry_index(self):
        with self.store.connect() as db:
            constraints=db.execute("SELECT conname FROM pg_constraint WHERE connamespace='rotation'::regnamespace").fetchall()
            indexes=db.execute("SELECT indexname FROM pg_indexes WHERE schemaname='rotation'").fetchall()
        self.assertGreaterEqual(len(constraints),10)
        self.assertIn(('nonces_created_idx',),indexes)
        with self.assertRaises(StoreUnavailable):
            with self.store.connect() as db:
                db.execute("INSERT INTO rotation.nonces VALUES('test','invalid',0)")

    def test_freshness_signature_ranking_and_http_responses(self):
        wrong=signed_headers(self.raw,Ed25519PrivateKey.generate(),'test',self.now)
        self.assertEqual(self.post(headers=wrong).status_code,401)
        partial=fake_public(self.now);del partial['returns']['5d']['XLV']
        self.assertEqual(self.post(json.dumps(partial).encode()).status_code,422)
        self.assertEqual(self.counts(),(0,0))
        self.assertEqual(self.post().status_code,200)
        data=self.app.test_client().get('/api/rotation').get_json()
        self.assertEqual(len(data['ranking']),14)
        self.assertEqual(data['result']['regime'],'CONFIRMED_RELATIVE_ROTATION')
        self.now += timedelta(days=1)
        stale=self.app.test_client().get('/api/rotation').get_json()
        self.assertEqual(stale['result']['status'],'BLOCKED')
        self.assertNotIn('ranking',stale)

    def test_capacity_bound_and_pruning(self):
        with self.store.connect(write=True) as db:
            with db.cursor() as cur:
                cur.executemany('INSERT INTO rotation.nonces VALUES(%s,%s,%s)',
                    [('test',f'{i:032x}',int(self.now.timestamp())) for i in range(4096)])
        self.assertEqual(self.post().status_code,429)
        self.assertEqual(self.counts(),(0,4096))
        with self.store.connect(write=True) as db:
            db.execute('UPDATE rotation.nonces SET created=%s',(int(self.now.timestamp())-602,))
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.counts(),(1,1))

    def test_future_timestamp_nonce_retained_full_validity_window(self):
        headers=signed_headers(self.raw,self.key,'test',self.now+timedelta(seconds=300))
        self.assertEqual(self.post(headers=headers).status_code,200)
        self.now += timedelta(seconds=600)
        self.assertEqual(self.post(headers=headers).status_code,409)
        self.now += timedelta(seconds=1)
        self.assertEqual(self.post(headers=headers).status_code,401)

    def test_initial_cutover_rejects_old_signature_after_migration(self):
        with self.store.connect(write=True) as db:
            db.execute('UPDATE rotation.schema_version SET signature_not_before=%s',(int(self.now.timestamp())+301,))
        old=signed_headers(self.raw,self.key,'test',self.now+timedelta(seconds=300))
        self.assertEqual(self.post(headers=old).get_json()['error_code'],'CUTOVER_GUARD')
        self.assertEqual(self.counts(),(0,0))
        self.now += timedelta(seconds=301)
        self.assertEqual(self.post(headers=old).status_code,503)
        self.assertEqual(self.post().status_code,200)

    def test_read_failure_hides_ranking_and_secrets(self):
        with patch.object(PublicStore,'latest',side_effect=StoreUnavailable('STORE_UNAVAILABLE')):
            data=self.app.test_client().get('/api/rotation').get_json()
        self.assertEqual(data['result']['reason'],'STORE_UNAVAILABLE')
        self.assertNotIn('ranking',data)
