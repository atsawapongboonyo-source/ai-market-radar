"""Transactional public-summary storage. Never log driver exceptions/DSNs.

Postgres writers serialize with one transaction-scoped advisory lock, including
empty-store inserts, nonce capacity checks, pruning and rollback checks. Every
accepted nonce and publication commits together; failed transactions roll back.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import sqlite3


class StoreUnavailable(Exception):
    """Fixed safe error; driver text may contain credentials."""


class PublicStore:
    def __init__(self, database):
        self.database = database
        self.postgres = isinstance(database, str) and database.startswith(('postgres://', 'postgresql://'))

    def __repr__(self):
        return f'PublicStore(backend={"postgresql" if self.postgres else "sqlite"})'

    @contextmanager
    def connect(self, *, write=False, migrate=False, rollback=False):
        db = None
        try:
            if self.postgres:
                import psycopg
                db = psycopg.connect(self.database, connect_timeout=5,
                    options='-c statement_timeout=5000 -c lock_timeout=4000 -c idle_in_transaction_session_timeout=10000',
                    application_name='rotation-staging')
                with db.transaction(force_rollback=rollback):
                    if write or migrate:
                        db.execute('SELECT pg_advisory_xact_lock(728194306125)')
                    yield db
            else:
                db = sqlite3.connect(self.database, timeout=5)
                db.execute('PRAGMA cache_size=-128')
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA wal_autocheckpoint=16')
                db.execute('PRAGMA journal_size_limit=65536')
                db.execute('PRAGMA max_page_count=1024')
                db.execute('CREATE TABLE IF NOT EXISTS publications(session TEXT PRIMARY KEY, generated TEXT, digest TEXT, body BLOB)')
                db.execute('CREATE TABLE IF NOT EXISTS nonces(key_id TEXT, nonce TEXT, created INTEGER, PRIMARY KEY(key_id,nonce))')
                db.commit()
                with db:
                    if write:
                        db.execute('BEGIN IMMEDIATE')
                    yield db
        except Exception:
            # Never propagate DSNs, passwords, SQL parameters or provider bodies.
            raise StoreUnavailable('STORE_UNAVAILABLE') from None
        finally:
            if db is not None:
                db.close()

    def execute(self, db, sql, params=()):
        return db.execute(sql.replace('?', '%s') if self.postgres else sql, params)

    def migrate(self):
        """Additive/idempotent migration, isolated schema; no SQLite file removed."""
        if not self.postgres:
            with self.connect():
                pass
            return
        with self.connect(migrate=True) as db:
            db.execute('CREATE SCHEMA IF NOT EXISTS rotation')
            db.execute('''CREATE TABLE IF NOT EXISTS rotation.schema_version (
                version INTEGER PRIMARY KEY CHECK(version=1),
                signature_not_before BIGINT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS rotation.publications (
                session DATE PRIMARY KEY,
                generated TIMESTAMPTZ NOT NULL,
                digest TEXT NOT NULL CHECK(digest ~ '^[a-f0-9]{64}$'),
                body BYTEA NOT NULL CHECK(octet_length(body) BETWEEN 1 AND 8192))''')
            db.execute('''CREATE TABLE IF NOT EXISTS rotation.nonces (
                key_id TEXT NOT NULL CHECK(key_id ~ '^[A-Za-z0-9_-]{1,48}$'),
                nonce TEXT NOT NULL CHECK(nonce ~ '^[a-f0-9]{32}$'),
                created BIGINT NOT NULL CHECK(created >= 0),
                PRIMARY KEY(key_id, nonce))''')
            db.execute('CREATE INDEX IF NOT EXISTS nonces_created_idx ON rotation.nonces(created)')
            # Old ephemeral SQLite nonces cannot be read by a replacement instance.
            # Exclude ALL pre-cutover signatures, including +300 s future skew.
            db.execute('''INSERT INTO rotation.schema_version VALUES
                (1, floor(extract(epoch FROM clock_timestamp()))::bigint + 301)
                ON CONFLICT DO NOTHING''')

    def table(self, name):
        return 'rotation.' + name if self.postgres else name

    def latest(self):
        with self.connect() as db:
            row = self.execute(db, f'SELECT body FROM {self.table("publications")} ORDER BY session DESC LIMIT 1').fetchone()
            return bytes(row[0]) if row else None

    def publish(self, raw, value, key_id, nonce, now, *, signed_timestamp=None):
        digest = hashlib.sha256(raw).hexdigest()
        generated = datetime.fromisoformat(value['generated_utc'].replace('Z', '+00:00'))
        p, n = self.table('publications'), self.table('nonces')
        with self.connect(write=True) as db:
            if self.postgres:
                floor = db.execute('SELECT signature_not_before FROM rotation.schema_version WHERE version=1').fetchone()
                if floor is None or int(signed_timestamp if signed_timestamp is not None else now.timestamp()) < floor[0]:
                    return 'CUTOVER_GUARD', 503
            # Timestamp validation allows +/-300 s. Retain for >600 s from
            # acceptance so even future-dated signed requests cannot replay.
            self.execute(db, f'DELETE FROM {n} WHERE created < ?', (int(now.timestamp())-601,))
            if self.execute(db, f'SELECT 1 FROM {n} WHERE key_id=? AND nonce=?', (key_id, nonce)).fetchone():
                return 'REPLAY_REJECTED', 409
            if self.execute(db, f'SELECT COUNT(*) FROM {n}').fetchone()[0] >= 4096:
                return 'INGEST_CAPACITY', 429
            self.execute(db, f'INSERT INTO {n}(key_id,nonce,created) VALUES(?,?,?)', (key_id, nonce, int(now.timestamp())))
            previous = self.execute(db, f'SELECT generated,digest FROM {p} WHERE session=?', (value['session_date'],)).fetchone()
            if previous:
                if previous[1] == digest:
                    return 'UNCHANGED', 200
                prior_time = previous[0] if self.postgres else datetime.fromisoformat(previous[0])
                if prior_time >= generated:
                    return 'ROLLBACK_REJECTED', 409
            self.execute(db, f'''INSERT INTO {p}(session,generated,digest,body) VALUES(?,?,?,?)
                ON CONFLICT(session) DO UPDATE SET generated=excluded.generated,
                digest=excluded.digest,body=excluded.body''',
                (value['session_date'], generated if self.postgres else generated.isoformat(), digest, raw))
            self.execute(db, f'DELETE FROM {p} WHERE session NOT IN (SELECT session FROM {p} ORDER BY session DESC LIMIT 32)')
        return 'ACCEPTED', 200
