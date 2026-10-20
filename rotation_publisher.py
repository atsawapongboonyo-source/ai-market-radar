"""Explicit opt-in public-only publisher. Existing Scheduled Task is unchanged.

Signing keys are separate from Alpaca credentials. Never transmit local evidence.
Production hostname is denied in this staging implementation.
"""
from datetime import date, datetime, timezone
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from rotation_public_protocol import parse_public, signature_message, PublicDataError, INGEST_PATH


def public_projection(evidence, now):
    from capital_rotation_automation import valid_saved
    from capital_rotation_calendar import last_completed_session
    day = last_completed_session(now)
    if not valid_saved(evidence, day):
        raise PublicDataError('LOCAL_VALIDATION_FAILED')
    # Recompute audit from observations, do not trust supplied audit return values.
    from capital_rotation_alpaca import _daily_close_snapshot
    payload = {'bars': {s: [{'t': r['bar_timestamp_utc'], 'c': r['close']} for r in records]
                        for s, records in evidence['observations'].items()}}
    snapshot = _daily_close_snapshot(payload, expected_session=day)
    projection = {'schema_version': 1, 'session_date': day.isoformat(),
                  'generated_utc': evidence['generated_utc'], 'feed': 'iex',
                  'returns': {w: {s: r['return_pct'] for s, r in snapshot[w].items()}
                              for w in ('5d', '20d')}}
    raw = json.dumps(projection, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    parse_public(raw, now)
    return raw


def signed_headers(raw, private_key, key_id, now, nonce=None):
    timestamp = str(int(now.timestamp()))
    nonce = nonce or secrets.token_hex(16)
    signature = private_key.sign(signature_message(raw, timestamp, nonce, key_id))
    return {'Content-Type': 'application/json', 'X-Rotation-Key-Id': key_id,
            'X-Rotation-Timestamp': timestamp, 'X-Rotation-Nonce': nonce,
            'X-Rotation-Signature': signature.hex()}


def validate_endpoint(url, *, local_staging=False):
    parsed = urlsplit(url)
    if (parsed.hostname == 'ai-market-radar-h08w.onrender.com' or parsed.path != INGEST_PATH
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise PublicDataError('DESTINATION_NOT_APPROVED')
    if parsed.scheme != 'https' and not (local_staging and parsed.scheme == 'http'
            and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise PublicDataError('HTTPS_REQUIRED')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise PublicDataError('REDIRECT_REFUSED')


def upload(url, raw, private_key, key_id, *, now=None, local_staging=False):
    now = now or datetime.now(timezone.utc)
    validate_endpoint(url, local_staging=local_staging)
    parse_public(raw, now)
    request = Request(url, data=raw, headers=signed_headers(raw, private_key, key_id, now), method='POST')
    try:
        with build_opener(NoRedirect()).open(request, timeout=12) as response:
            return response.status
    except Exception:
        raise PublicDataError('PUBLICATION_FAILED') from None


def dpapi(data, *, decrypt=False):
    if os.name != 'nt':
        raise PublicDataError('WINDOWS_REQUIRED')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    output = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = library.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = library.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    try:
        if not ok:
            raise PublicDataError('SIGNING_KEY_UNAVAILABLE')
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if output.data:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)


def create_signing_key(path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.generate()
    encrypted = dpapi(private.private_bytes_raw())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # This path must be in an ACL-protected collector directory, never Git.
    with path.open('xb') as handle:
        handle.write(encrypted)
    return private.public_key().public_bytes_raw().hex()


def load_signing_key(path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(dpapi(Path(path).read_bytes(), decrypt=True))
