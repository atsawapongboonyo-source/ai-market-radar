"""Existing staging service, signed real summaries only; no provider credentials."""
from pathlib import Path
import json
import tempfile
import os
from scanner import app as scanner_app
from rotation_web import RotationSite
from rotation_store import PublicStore, StoreUnavailable
from rotation_backup import restore_drill

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
store = PublicStore(database)
store.migrate()
if storage_mode == 'POSTGRESQL_PERSISTENT':
    # Safe evidence only. No DSN, credentials, bodies, signatures or nonce values.
    # Staging startup verifies a snapshot in temporary tables; live rows unchanged.
    print(json.dumps({'event': 'ROTATION_STORAGE_VERIFICATION',
        'database_variable_present': bool(os.environ.get('ROTATION_DATABASE_URL')),
        'storage_mode': storage_mode, 'restore_drill': restore_drill(store)}), flush=True)
app = RotationSite(scanner_app, database=database,
    public_keys=public['public_keys'], trusted_tls_proxy=True, loopback_staging=True,
    simulated=False, storage_mode=storage_mode)

# Feature branch only: no stock hooks are installed in the original scanner app.
from rotation_stock_store import StockStore
from rotation_stock_web import register_stock
stock_universe = json.loads((Path(__file__).parent/'data'/'rotation-stock-universe-v1.json').read_text())
stock_store = StockStore(database)
stock_store.migrate()
stock_current = register_stock(app.rotation_app, stock_store, public['public_keys'], stock_universe)

from rotation_opportunities import install_opportunities
install_opportunities(scanner_app, app.rotation_app, stock_current)

# Navigation is opt-in at this staging entrypoint; production scanner is untouched.
from rotation_navigation import install_navigation
install_navigation(scanner_app, scanner=True)
install_navigation(app.rotation_app)

# Read-only research directory is mounted only on this staging application.
from stock_radar_research_web import install_research_directory
install_research_directory(app.rotation_app)
