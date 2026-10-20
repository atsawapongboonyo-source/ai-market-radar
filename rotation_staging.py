"""Separate staging service: simulated data only, no Alpaca or environment edits.

Receives signed synthetic summaries using the staging-only public key file.
No simulation is injected into production and no server monitor is enabled here.
"""
from pathlib import Path
import json
import tempfile
from scanner import app as scanner_app
from rotation_web import RotationSite

public = json.loads((Path(__file__).parent/'rotation-staging-public.json').read_text(encoding='utf-8'))
app = RotationSite(scanner_app, database=str(Path(tempfile.gettempdir())/'rotation-staging.sqlite'),
    public_keys=public['public_keys'], trusted_tls_proxy=True, loopback_staging=True, simulated=True)
