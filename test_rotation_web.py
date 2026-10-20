from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing
import unittest
from unittest.mock import patch

from flask import Flask
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rotation_public_protocol import SYMBOLS, INGEST_PATH
from rotation_publisher import signed_headers, validate_endpoint
from rotation_web import register_rotation, NAV


def fake_public(now):
    from capital_rotation_calendar import last_completed_session
    values = {s: (1 if s == 'SPY' else 0 if s in ('SMH','SOXX') else 3) for s in SYMBOLS}
    return {'schema_version': 1, 'session_date': last_completed_session(now).isoformat(),
            'generated_utc': now.isoformat(), 'feed': 'iex',
            'returns': {w: dict(values) for w in ('5d','20d')}}


class RotationWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name)/'public.sqlite')
        self.key = Ed25519PrivateKey.generate()
        self.now = datetime(2026,10,20,12,tzinfo=timezone.utc)
        self.app = Flask(__name__)
        @self.app.get('/')
        def home():
            return '<html><body>Original Scanner</body></html>'
        @self.app.get('/api/unchanged')
        def unchanged():
            return {'score':72,'engine':'V4.10'}
        register_rotation(self.app, database=self.db,
            public_keys={'test':self.key.public_key().public_bytes_raw().hex()},
            clock=lambda:self.now, loopback_staging=True, simulated=True)
        self.client = self.app.test_client()

    def post(self, value=None, *, headers=None):
        raw = json.dumps(fake_public(self.now) if value is None else value).encode()
        return self.client.post(INGEST_PATH,data=raw,
            headers=headers or signed_headers(raw,self.key,'test',self.now))

    def test_signed_public_data_is_recomputed_and_no_private_fields_returned(self):
        self.assertEqual(self.post().status_code,200)
        data=self.client.get('/api/rotation').get_json()
        self.assertEqual(data['result']['regime'],'CONFIRMED_RELATIVE_ROTATION')
        self.assertFalse(data['result']['trade_signal'])
        self.assertNotIn('observations',data)
        self.assertNotIn('calculation_audit',data)
        page=self.client.get('/rotation')
        self.assertIn(b'SIMULATED STAGING',page.data)
        self.assertEqual(page.headers['Cache-Control'],'no-store')

    def test_replay_persists_across_app_instances(self):
        raw=json.dumps(fake_public(self.now)).encode()
        headers=signed_headers(raw,self.key,'test',self.now)
        self.assertEqual(self.client.post(INGEST_PATH,data=raw,headers=headers).status_code,200)
        app2=Flask('restart')
        register_rotation(app2,database=self.db,public_keys={'test':self.key.public_key().public_bytes_raw().hex()},clock=lambda:self.now,loopback_staging=True)
        self.assertEqual(app2.test_client().post(INGEST_PATH,data=raw,headers=headers).status_code,409)

    def test_idempotent_repeat_with_new_nonce_has_one_record(self):
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post().get_json()['status'],'UNCHANGED')
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM publications').fetchone()[0],1)

    def test_private_fields_and_partial_coverage_are_rejected(self):
        value=fake_public(self.now);value['observations']={'private':'do-not-upload'}
        self.assertEqual(self.post(value).status_code,422)
        value=fake_public(self.now);del value['returns']['5d']['XLV']
        self.assertEqual(self.post(value).status_code,422)

    def test_invalid_signature_and_expired_timestamp(self):
        raw=json.dumps(fake_public(self.now)).encode()
        headers=signed_headers(raw,Ed25519PrivateKey.generate(),'test',self.now)
        self.assertEqual(self.post(headers=headers).status_code,401)
        headers=signed_headers(raw,self.key,'test',self.now-timedelta(minutes=6))
        self.assertEqual(self.post(headers=headers).status_code,401)

    def test_stale_data_fail_closed_on_get(self):
        self.post()
        self.now += timedelta(days=1)
        data=self.client.get('/api/rotation').get_json()
        self.assertEqual(data['result']['status'],'BLOCKED')
        self.assertEqual(data['result']['candidates'],[])

    def test_rollback_rejected(self):
        self.post()
        value=fake_public(self.now);value['generated_utc']=(self.now-timedelta(minutes=1)).isoformat()
        self.assertEqual(self.post(value).status_code,409)

    def test_oversize_and_duplicate_json_and_nonfinite_rejected(self):
        response=self.client.post(INGEST_PATH,data=b'x'*9000,content_type='application/json')
        self.assertEqual(response.status_code,413)
        value=fake_public(self.now);value['returns']['5d']['SPY']=float('nan')
        self.assertEqual(self.post(value).status_code,422)
        raw=b'{"schema_version":1,"schema_version":1}'
        self.assertEqual(self.client.post(INGEST_PATH,data=raw,headers=signed_headers(raw,self.key,'test',self.now)).status_code,422)

    def test_https_required_outside_loopback(self):
        raw=json.dumps(fake_public(self.now)).encode()
        self.assertEqual(self.client.post(INGEST_PATH,data=raw,headers=signed_headers(raw,self.key,'test',self.now),environ_base={'REMOTE_ADDR':'192.0.2.1'}).status_code,400)

    def test_unconfigured_ingress_is_disabled(self):
        app=Flask('disabled');register_rotation(app)
        self.assertEqual(app.test_client().post(INGEST_PATH).status_code,503)
        self.assertEqual(app.test_client().get('/api/rotation').get_json()['result']['candidates'],[])

    def test_navigation_does_not_change_original_api(self):
        self.assertEqual(self.client.get('/api/unchanged').get_json(),{'score':72,'engine':'V4.10'})
        self.assertEqual(self.client.get('/').get_data(as_text=True).replace(NAV,''),'<html><body>Original Scanner</body></html>')

    def test_production_upload_and_redirect_destinations_not_allowed(self):
        for url in ('https://ai-market-radar-h08w.onrender.com/api/rotation/ingest',
                    'http://example.org/api/rotation/ingest',
                    'https://example.org/other', 'https://user:pass@example.org/api/rotation/ingest'):
            with self.assertRaises(ValueError):
                validate_endpoint(url)

    def test_wsgi_isolation_keeps_scanner_hooks_out_of_rotation(self):
        from rotation_web import RotationSite
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        base=Flask('scanner_hooks')
        @base.get('/')
        def original(): return '<body>Scanner</body>'
        @base.after_request
        def scanner_hook(response):
            response.set_data(response.get_data(as_text=True).replace('</body>','<script>legacyMarker()</script></body>'))
            return response
        functions=dict(base.view_functions)
        site=RotationSite(base)
        client=Client(site,Response)
        self.assertNotIn(b'legacyMarker',client.get('/rotation').data)
        self.assertIn(b'legacyMarker',client.get('/').data)
        self.assertEqual(base.view_functions,functions)

    def test_projection_drops_private_audit_and_rejects_tampering(self):
        from capital_rotation_automation import run_once
        from test_capital_rotation_automation import snapshot_for
        from rotation_publisher import public_projection
        root=Path(self.tmp.name)/'collector'
        run_once(root,now=self.now,fetcher=lambda **kw:snapshot_for(kw['expected_session']))
        evidence=json.loads((root/'daily'/'2026-10-19.json').read_text())
        evidence['private_note']='do-not-transmit-this'
        raw=public_projection(evidence,self.now)
        for forbidden in (b'do-not-transmit',b'observations',b'calculation_audit',b'close',b'owner_sid'):
            self.assertNotIn(forbidden,raw)
        evidence['observations']['SPY'][0]['close']=1234
        with self.assertRaises(ValueError): public_projection(evidence,self.now)

    @unittest.skipUnless(__import__('os').name=='nt','Windows DPAPI')
    def test_signing_private_key_is_dpapi_encrypted(self):
        from rotation_publisher import create_signing_key,load_signing_key
        path=Path(self.tmp.name)/'staging.dpapi'
        public=create_signing_key(path)
        private=load_signing_key(path)
        self.assertEqual(private.public_key().public_bytes_raw().hex(),public)
        self.assertNotIn(private.private_bytes_raw(),path.read_bytes())
        with self.assertRaises(FileExistsError): create_signing_key(path)


if __name__=='__main__':
    unittest.main()
