"""
Compatibility entrypoint for Render services still configured as:
    gunicorn scanner:app

The original V4.7.1 scanner implementation is preserved byte-for-byte in
legacy_scanner.py. We first mirror its module globals here so the V4.8/V4.9
extension chain can continue importing `scanner as base` safely, then expose
the final V4.9.2 Flask app.
"""

import legacy_scanner as _legacy

# Mirror every non-dunder global, including underscore-prefixed engine helpers
# used by the extension modules.
for _name, _value in vars(_legacy).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

# Load the full extension chain only after legacy globals exist in this module.
import scanner_v492 as _latest

app = _latest.app

# Keep a visible runtime marker for diagnostics.
RUNTIME_VERSION = "4.9.2"
