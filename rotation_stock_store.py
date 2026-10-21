"""Additive stock publications; uses the original global nonce/write lock.
Original 14-ETF publications and schema are never updated by this adapter.
"""
import hashlib
from datetime import datetime
from rotation_store import PublicStore,StoreUnavailable
class StockStore(PublicStore):
    def migrate(self):
        if not self.postgres:raise StoreUnavailable('POSTGRES_REQUIRED')
        with self.connect(migrate=True) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS rotation.stock_publications(
              session DATE PRIMARY KEY,generated TIMESTAMPTZ NOT NULL,
              digest TEXT NOT NULL CHECK(digest ~ '^[a-f0-9]{64}$'),
              body BYTEA NOT NULL CHECK(octet_length(body) BETWEEN 1 AND 131072))''')
    def latest(self):
        with self.connect() as db:
            r=db.execute('SELECT body FROM rotation.stock_publications ORDER BY session DESC LIMIT 1').fetchone()
            if not r:return None
            import json
            value=json.loads(bytes(r[0]));base=db.execute('SELECT body FROM rotation.publications WHERE session=%s',(value['session_date'],)).fetchone()
            if not base:raise StoreUnavailable('BASELINE_UNAVAILABLE')
            baseline=json.loads(bytes(base[0]))
            for row in value['stocks']:
                m=row['metrics']
                if m:
                    for w in (5,20):
                        if abs(m[f'etf_{w}d_pct']-baseline['returns'][f'{w}d'][row['parent']])>1e-5 or abs(m[f'spy_{w}d_pct']-baseline['returns'][f'{w}d']['SPY'])>1e-5:raise StoreUnavailable('BASELINE_MISMATCH')
            return bytes(r[0])
    def publish(self,raw,value,kid,nonce,now,*,signed_timestamp):
        digest=hashlib.sha256(raw).hexdigest();generated=datetime.fromisoformat(value['generated_utc'])
        with self.connect(write=True) as db:
            floor=db.execute('SELECT signature_not_before FROM rotation.schema_version WHERE version=1').fetchone()
            if not floor or signed_timestamp<floor[0]:return 'CUTOVER_GUARD',503
            db.execute('DELETE FROM rotation.nonces WHERE created < %s',(int(now.timestamp())-601,))
            if db.execute('SELECT 1 FROM rotation.nonces WHERE key_id=%s AND nonce=%s',(kid,nonce)).fetchone():return 'REPLAY_REJECTED',409
            if db.execute('SELECT count(*) FROM rotation.nonces').fetchone()[0]>=4096:return 'INGEST_CAPACITY',429
            # Bind stock summary to the already verified 14-ETF session and returns.
            base=db.execute('SELECT body FROM rotation.publications WHERE session=%s',(value['session_date'],)).fetchone()
            if not base:return 'BASELINE_REQUIRED',409
            import json
            baseline=json.loads(bytes(base[0]))
            for row in value['stocks']:
                m=row['metrics']
                if m:
                    for w in (5,20):
                        if abs(m[f'etf_{w}d_pct']-baseline['returns'][f'{w}d'][row['parent']])>1e-5 or abs(m[f'spy_{w}d_pct']-baseline['returns'][f'{w}d']['SPY'])>1e-5:return 'BASELINE_MISMATCH',422
            db.execute('INSERT INTO rotation.nonces VALUES(%s,%s,%s)',(kid,nonce,int(now.timestamp())))
            prior=db.execute('SELECT generated,digest FROM rotation.stock_publications WHERE session=%s',(value['session_date'],)).fetchone()
            if prior:
                if prior[1]==digest:return 'UNCHANGED',200
                if prior[0]>=generated:return 'ROLLBACK_REJECTED',409
            db.execute('''INSERT INTO rotation.stock_publications VALUES(%s,%s,%s,%s)
              ON CONFLICT(session) DO UPDATE SET generated=excluded.generated,digest=excluded.digest,body=excluded.body''',(value['session_date'],generated,digest,raw))
            db.execute('DELETE FROM rotation.stock_publications WHERE session NOT IN (SELECT session FROM rotation.stock_publications ORDER BY session DESC LIMIT 32)')
        return 'ACCEPTED',200
