"""Existing staging service, signed real summaries only; no provider credentials."""
from pathlib import Path
import json
import tempfile
import os
from scanner import app as scanner_app
from rotation_web import RotationSite
from rotation_store import PublicStore, StoreUnavailable

def staging_storage():
    # Optional nonsecret path. Never silently fall back when an approved mount fails.
    if 'ROTATION_DATABASE_URL' in os.environ:
        url = os.environ['ROTATION_DATABASE_URL']
        if not url.startswith(('postgresql://', 'postgres://')):
            raise StoreUnavailable('STORE_UNAVAILABLE')
        return url, 'POSTGRESQL_PERSISTENT'
    configured = os.environ.get('ROTATION_STAGING_DATA_DIR')
    mounted = os.path.ismount('/var/data')
    root = Path(configured) if configured else (Path('/var/data') if mounted else Path(tempfile.gettempdir()))
    return str(root/'rotation-staging.sqlite'), ('PERSISTENT_MOUNT' if mounted and root == Path('/var/data') else
        'CONFIGURED_UNVERIFIED' if configured else 'EPHEMERAL')


public = json.loads((Path(__file__).parent/'rotation-staging-public.json').read_text(encoding='utf-8'))
database, storage_mode = staging_storage()
# Fail startup safely if the configured database/migration is unavailable.
PublicStore(database).migrate()
app = RotationSite(scanner_app, database=database,
    public_keys=public['public_keys'], trusted_tls_proxy=True, loopback_staging=True,
    simulated=False, storage_mode=storage_mode)
