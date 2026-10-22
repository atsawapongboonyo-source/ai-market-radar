"""Opt-in WSGI entrypoint. Existing scanner modules are not modified.

Proposed start: gunicorn rotation_site:app. Not activated in production.
Only public-key configuration is read here; no Alpaca credentials belong here.
"""
import json
import os
from pathlib import Path
from scanner import app as scanner_app
from rotation_web import RotationSite

config = {}
path = os.environ.get('ROTATION_PUBLIC_CONFIG_PATH')
if path:
    config = json.loads(Path(path).read_text(encoding='utf-8'))
app = RotationSite(scanner_app, database=config.get('database'), public_keys=config.get('public_keys'),
                   trusted_tls_proxy=config.get('trusted_tls_proxy', False))
