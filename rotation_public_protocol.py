"""Strict public-only schema and domain-separated Ed25519 request signatures."""
from datetime import datetime, timezone
from math import isfinite
import hashlib
import json
import re

from capital_rotation_offline import SECTORS, AI_PROXIES
from capital_rotation_calendar import last_completed_session
from capital_rotation_confirmation import confirm_rotation

SYMBOLS = ('SPY',) + AI_PROXIES + SECTORS
MAX_BODY = 8192
INGEST_PATH = '/api/rotation/ingest'


class PublicDataError(ValueError):
    pass


def parse_public(raw, now):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PublicDataError('INVALID_SCHEMA')
            value[key] = item
        return value
    try:
        if len(raw) > MAX_BODY:
            raise PublicDataError('PAYLOAD_TOO_LARGE')
        value = json.loads(raw, object_pairs_hook=unique)
        if set(value) != {'schema_version', 'session_date', 'generated_utc', 'feed', 'returns'}:
            raise PublicDataError('INVALID_SCHEMA')
        if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['feed'] != 'iex':
            raise PublicDataError('INVALID_SCHEMA')
        if value['session_date'] != last_completed_session(now).isoformat():
            raise PublicDataError('STALE_SESSION')
        generated = datetime.fromisoformat(value['generated_utc'].replace('Z', '+00:00'))
        if generated.tzinfo is None or not -60 <= (now-generated).total_seconds() <= 120*3600:
            raise PublicDataError('STALE_PUBLICATION')
        if set(value['returns']) != {'5d', '20d'}:
            raise PublicDataError('INVALID_SCHEMA')
        for rows in value['returns'].values():
            if set(rows) != set(SYMBOLS):
                raise PublicDataError('INCOMPLETE_COVERAGE')
            for number in rows.values():
                if type(number) not in (int, float) or not isfinite(number) or not -100 < number <= 10000:
                    raise PublicDataError('INVALID_RETURN')
        analysis = confirm_rotation(value['returns'], {w: set(SYMBOLS) for w in ('5d', '20d')})
        return value, {'status': 'RESEARCH_ONLY', **analysis}
    except PublicDataError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PublicDataError('INVALID_SCHEMA') from None


def signature_message(raw, timestamp, nonce, key_id):
    return ('rotation-public-v1\nPOST\n' + INGEST_PATH + '\n' + key_id + '\n'
            + timestamp + '\n' + nonce + '\n' + hashlib.sha256(raw).hexdigest()).encode('ascii')


def verify_signature(raw, headers, public_keys, now):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        key_id = headers.get('X-Rotation-Key-Id', '')
        timestamp = headers.get('X-Rotation-Timestamp', '')
        nonce = headers.get('X-Rotation-Nonce', '')
        signature = headers.get('X-Rotation-Signature', '')
        if not re.fullmatch('[A-Za-z0-9_-]{1,48}', key_id) or key_id not in public_keys:
            raise ValueError()
        if not re.fullmatch('[0-9]{10}', timestamp) or abs(now.timestamp()-int(timestamp)) > 300:
            raise ValueError()
        if not re.fullmatch('[a-f0-9]{32}', nonce) or not re.fullmatch('[a-f0-9]{128}', signature):
            raise ValueError()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_keys[key_id])).verify(
            bytes.fromhex(signature), signature_message(raw, timestamp, nonce, key_id))
        return key_id, nonce
    except (ValueError, TypeError, InvalidSignature):
        raise PublicDataError('INVALID_SIGNATURE') from None
