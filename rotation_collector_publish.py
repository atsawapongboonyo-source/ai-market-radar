"""Opt-in extension of the installed collector; only strict public projections leave Windows."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

from capital_rotation_automation import read_json, write_json
from capital_rotation_calendar import last_completed_session
from rotation_public_protocol import PublicDataError
from rotation_publisher import load_signing_key, public_projection, upload

STAGING_ENDPOINT = 'https://ai-market-radar-rotation-staging.onrender.com/api/rotation/ingest'


def publish_once(root, *, now=None, sender=upload, key_loader=load_signing_key):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    status = {'status': 'BLOCKED', 'error_code': None, 'last_attempt_utc': now.isoformat(),
              'session_date': None, 'http_status': None, 'destination': 'STAGING'}
    try:
        config = read_json(root/'publisher.json')
        if config.get('enabled') is not True or config.get('endpoint') != STAGING_ENDPOINT:
            raise PublicDataError('PUBLISHER_NOT_CONFIGURED')
        health = read_json(root/'health.json')
        day = last_completed_session(now).isoformat()
        status['session_date'] = day
        checked = datetime.fromisoformat(health.get('last_check_utc', ''))
        if (health.get('status') not in ('OK', 'UP_TO_DATE') or health.get('latest_session') != day
                or checked.tzinfo is None or not 0 <= (now-checked).total_seconds() <= 1800):
            raise PublicDataError('COLLECTOR_NOT_HEALTHY')
        evidence = read_json(root/'daily'/(day+'.json'))
        raw = public_projection(evidence, now)
        # Local durable public outbox. Never copy private observations or audit files.
        from capital_rotation_storage import atomic_write_text
        atomic_write_text(root/'public-outbox'/(day+'.json'), raw.decode('utf-8'))
        private = key_loader(root/'secrets'/'rotation-staging-real-signing.dpapi')
        http = sender(STAGING_ENDPOINT, raw, private, 'windows-staging-real', now=now)
        if http != 200:
            raise PublicDataError('PUBLICATION_FAILED')
        status.update(status='PUBLISHED', http_status=http,
                      public_sha256=hashlib.sha256(raw).hexdigest())
    except PublicDataError as exc:
        allowed = {'PUBLISHER_NOT_CONFIGURED', 'COLLECTOR_NOT_HEALTHY', 'LOCAL_VALIDATION_FAILED',
                   'STALE_SESSION', 'STALE_PUBLICATION', 'PUBLICATION_FAILED'}
        status['error_code'] = str(exc) if str(exc) in allowed else 'PUBLICATION_BLOCKED'
    except Exception:
        # Never record exception text, provider bodies, file content or credentials.
        status['error_code'] = 'PUBLISHER_UNAVAILABLE'
    write_json(root/'publication-health.json', status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = publish_once(args.root)
        print(json.dumps(result))
        return 0 if result['status'] == 'PUBLISHED' else 2
    except Exception:
        print('{"status":"BLOCKED","error_code":"PUBLISHER_UNAVAILABLE"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
