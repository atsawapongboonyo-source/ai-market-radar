"""Additive Flask extension: bounded public data only, no Alpaca imports/calls."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
from contextlib import contextmanager

from flask import Blueprint, jsonify, render_template, request
from rotation_public_protocol import (MAX_BODY, INGEST_PATH, PublicDataError,
                                      parse_public, verify_signature)

NAV = '<nav id="capital-rotation-nav" style="padding:8px 16px;background:#0d1b2a"><a href="/rotation" style="color:#93c5fd">Capital Rotation Dashboard →</a></nav>'


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=1)
    try:
        db.execute('PRAGMA cache_size=-128')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=16')
        db.execute('PRAGMA journal_size_limit=65536')
        db.execute('PRAGMA max_page_count=1024')
        db.execute('CREATE TABLE IF NOT EXISTS publications(session TEXT PRIMARY KEY, generated TEXT, digest TEXT, body BLOB)')
        db.execute('CREATE TABLE IF NOT EXISTS nonces(key_id TEXT, nonce TEXT, created INTEGER, PRIMARY KEY(key_id,nonce))')
        with db:
            yield db
    finally:
        db.close()


def register_rotation(app, *, database=None, public_keys=None, clock=None,
                      loopback_staging=False, trusted_tls_proxy=False, simulated=False,
                      storage_mode='UNVERIFIED'):
    clock = clock or (lambda: datetime.now(timezone.utc))
    public_keys = public_keys or {}
    configured = bool(database and public_keys)
    bp = Blueprint('capital_rotation', __name__, template_folder='rotation_templates')

    def blocked(code):
        return {'status': 'BLOCKED', 'reason': code, 'candidates': [], 'trade_signal': False}

    def current():
        if not configured:
            return {'result': blocked('INGEST_NOT_CONFIGURED'), 'simulated': simulated}
        try:
            with connection(database) as db:
                row = db.execute('SELECT body FROM publications ORDER BY session DESC LIMIT 1').fetchone()
            if not row:
                return {'result': blocked('AWAITING_COLLECTOR'), 'simulated': simulated}
            value, result = parse_public(bytes(row[0]), clock())
            ranking = sorted(({'symbol': s, 'return_5d_pct': value['returns']['5d'][s],
                'return_20d_pct': value['returns']['20d'][s],
                'relative_5d_pct': round(value['returns']['5d'][s]-value['returns']['5d']['SPY'], 3),
                'relative_20d_pct': round(value['returns']['20d'][s]-value['returns']['20d']['SPY'], 3)}
                for s in value['returns']['5d']),
                key=lambda r: (-r['relative_20d_pct'], -r['relative_5d_pct'], r['symbol']))
            return {'result': result, 'session_date': value['session_date'],
                    'generated_utc': value['generated_utc'], 'returns': value['returns'],
                    'feed': 'iex', 'simulated': simulated, 'ranking': ranking}
        except PublicDataError as exc:
            return {'result': blocked(str(exc)), 'simulated': simulated}
        except (OSError, sqlite3.Error):
            return {'result': blocked('STORE_UNAVAILABLE'), 'simulated': simulated}

    @bp.get('/rotation')
    def dashboard():
        return render_template('rotation_dashboard.html', data=current(), storage_mode=storage_mode)

    @bp.get('/api/rotation')
    def read_rotation():
        return jsonify(current())

    @bp.post(INGEST_PATH)
    def ingest():
        def error(code, status):
            return jsonify({'ok': False, 'error_code': code}), status
        if not configured:
            return error('INGEST_NOT_CONFIGURED', 503)
        local = loopback_staging and request.remote_addr in ('127.0.0.1', '::1')
        secure = request.is_secure or (trusted_tls_proxy and request.headers.get('X-Forwarded-Proto') == 'https')
        if not (local or secure):
            return error('HTTPS_REQUIRED', 400)
        if request.content_length is None:
            return error('CONTENT_LENGTH_REQUIRED', 411)
        if request.content_length > MAX_BODY:
            return error('PAYLOAD_TOO_LARGE', 413)
        if request.mimetype != 'application/json':
            return error('JSON_REQUIRED', 415)
        raw = request.stream.read(MAX_BODY+1)
        now = clock()
        try:
            key_id, nonce = verify_signature(raw, request.headers, public_keys, now)
            value, _ = parse_public(raw, now)
            digest = hashlib.sha256(raw).hexdigest()
            with connection(database) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM nonces WHERE created < ?', (int(now.timestamp())-600,))
                if db.execute('SELECT COUNT(*) FROM nonces').fetchone()[0] >= 4096:
                    return error('INGEST_CAPACITY', 429)
                try:
                    db.execute('INSERT INTO nonces VALUES(?,?,?)', (key_id, nonce, int(now.timestamp())))
                except sqlite3.IntegrityError:
                    return error('REPLAY_REJECTED', 409)
                previous = db.execute('SELECT generated,digest FROM publications WHERE session=?', (value['session_date'],)).fetchone()
                if previous:
                    if previous[1] == digest:
                        return jsonify({'ok': True, 'status': 'UNCHANGED'})
                    if datetime.fromisoformat(previous[0]) >= datetime.fromisoformat(value['generated_utc'].replace('Z','+00:00')):
                        return error('ROLLBACK_REJECTED', 409)
                generated = datetime.fromisoformat(value['generated_utc'].replace('Z','+00:00')).isoformat()
                db.execute('INSERT OR REPLACE INTO publications VALUES(?,?,?,?)', (value['session_date'], generated, digest, raw))
                db.execute('DELETE FROM publications WHERE session NOT IN (SELECT session FROM publications ORDER BY session DESC LIMIT 32)')
            return jsonify({'ok': True, 'status': 'ACCEPTED'})
        except PublicDataError as exc:
            return error(str(exc), 401 if str(exc) == 'INVALID_SIGNATURE' else 422)
        except (sqlite3.Error, OSError):
            return error('STORE_UNAVAILABLE', 503)

    @bp.after_request
    def safe_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        return response

    app.register_blueprint(bp)

    @app.after_request
    def navigation(response):
        if request.path in ('/', '/scanner') and response.status_code == 200 and response.mimetype == 'text/html' and not response.direct_passthrough:
            body = response.get_data(as_text=True)
            if 'id="capital-rotation-nav"' not in body:
                response.set_data(body.replace('</body>', NAV + '</body>', 1))
        return response

    return app


class RotationSite:
    """Dispatch Rotation to its own Flask app, isolated from scanner HTML hooks."""
    def __init__(self, scanner_app, **settings):
        from flask import Flask
        self.scanner_app = scanner_app
        self.rotation_app = Flask('capital_rotation_isolated')
        register_rotation(self.rotation_app, **settings)

        @scanner_app.after_request
        def rotation_link(response):
            if request.path in ('/', '/scanner') and response.status_code == 200 and response.mimetype == 'text/html' and not response.direct_passthrough:
                body = response.get_data(as_text=True)
                if 'id="capital-rotation-nav"' not in body:
                    response.set_data(body.replace('</body>', NAV+'</body>', 1))
            return response

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path in ('/rotation', '/api/rotation') or path.startswith(('/rotation/', '/api/rotation/')):
            return self.rotation_app(environ, start_response)
        return self.scanner_app(environ, start_response)
