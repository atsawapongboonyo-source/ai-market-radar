"""Explicit signed SIMULATED staging upload. Never reads Alpaca/audit files."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rotation_simulation import simulated_publication
from rotation_publisher import load_signing_key, upload

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--endpoint', required=True)
parser.add_argument('--key-file', type=Path, required=True)
parser.add_argument('--local', action='store_true')
args=parser.parse_args()
now=datetime.now(timezone.utc)
raw=json.dumps(simulated_publication(now),sort_keys=True,separators=(',',':')).encode()
status=upload(args.endpoint,raw,load_signing_key(args.key_file),'windows-staging',now=now,local_staging=args.local)
print(json.dumps({'simulation_only':True,'http_status':status,'private_audit_read':False,'alpaca_credentials_read':False}))
