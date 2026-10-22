"""Bounded logical backup/restore drill; source tables are never modified.

A repeatable-read snapshot is serialized to JSON, deserialized and restored to
connection-local temporary tables with matching constraints/indexes. Every row
is compared in both directions; transaction is rolled back, even on failure.
This verifies application-level recovery, not Render PITR or instance recovery.
"""
import base64
import json
from rotation_store import StoreUnavailable


def restore_drill(store):
    if not store.postgres:
        raise StoreUnavailable('POSTGRES_REQUIRED')
    with store.connect(rollback=True) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        pubs = db.execute('SELECT session::text, generated::text, digest, body FROM rotation.publications ORDER BY session').fetchall()
        nonces = db.execute('SELECT key_id,nonce,created FROM rotation.nonces ORDER BY key_id,nonce').fetchall()
        meta = db.execute('SELECT version,signature_not_before FROM rotation.schema_version').fetchall()
        stock_exists = db.execute("SELECT to_regclass('rotation.stock_publications') IS NOT NULL").fetchone()[0]
        stocks = (db.execute('SELECT session::text, generated::text, digest, body FROM rotation.stock_publications ORDER BY session').fetchall() if stock_exists else [])
        encoded = json.dumps({'publications': [[a,b,c,base64.b64encode(bytes(d)).decode('ascii')] for a,b,c,d in pubs],
                              'nonces': nonces, 'schema_version': meta,
                              'stock_publications': [[a,b,c,base64.b64encode(bytes(d)).decode('ascii')] for a,b,c,d in stocks]}, sort_keys=True).encode()
        restored = json.loads(encoded)
        for table in ('publications', 'nonces', 'schema_version'):
            db.execute(f'CREATE TEMP TABLE restore_{table} (LIKE rotation.{table} INCLUDING ALL) ON COMMIT DROP')
        if stock_exists:
            db.execute('CREATE TEMP TABLE restore_stock_publications (LIKE rotation.stock_publications INCLUDING ALL) ON COMMIT DROP')
            for a,b,c,d in restored['stock_publications']:
                db.execute('INSERT INTO restore_stock_publications VALUES(%s,%s,%s,%s)', (a,b,c,base64.b64decode(d,validate=True)))
        for a,b,c,d in restored['publications']:
            db.execute('INSERT INTO restore_publications VALUES(%s,%s,%s,%s)', (a,b,c,base64.b64decode(d,validate=True)))
        for row in restored['nonces']:
            db.execute('INSERT INTO restore_nonces VALUES(%s,%s,%s)', row)
        for row in restored['schema_version']:
            db.execute('INSERT INTO restore_schema_version VALUES(%s,%s)', row)
        for table in ('publications', 'nonces', 'schema_version') + (('stock_publications',) if stock_exists else ()):
            differences = db.execute(f'''SELECT COUNT(*) FROM (
                (SELECT * FROM rotation.{table} EXCEPT SELECT * FROM restore_{table})
                UNION ALL (SELECT * FROM restore_{table} EXCEPT SELECT * FROM rotation.{table})) AS difference''').fetchone()[0]
            if differences:
                raise StoreUnavailable('RESTORE_MISMATCH')
        return {'status': 'VERIFIED', 'publications': len(pubs), 'nonces': len(nonces),
                'serialized_bytes': len(encoded), 'stock_publications': len(stocks),
                'stock_table_present': stock_exists, 'source_modified': False,
                'scope': 'logical snapshot to temporary tables; not PITR'}
