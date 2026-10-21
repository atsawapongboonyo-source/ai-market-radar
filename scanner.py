"""
Compatibility entrypoint for Render services still configured as:
    gunicorn scanner:app

The original V4.7.1 implementation lives unchanged in legacy_scanner.py.
During extension loading we temporarily alias the module name `scanner` to the
legacy module so all V4.8/V4.9 monkey patches modify the SAME globals used by
Flask's already-registered routes. Then we restore this lightweight wrapper and
expose the final V5.3.1 app while keeping the V4.10 execution engine intact.
"""

import sys as _sys
import legacy_scanner as _legacy

# Export legacy names for compatibility with any direct scanner imports.
for _name, _value in vars(_legacy).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

_wrapper = _sys.modules[__name__]

# Critical: extension modules import `scanner as base`. Point that import at the
# legacy module while the chain loads so its routes and engine share one state.
_sys.modules["scanner"] = _legacy
try:
    import scanner_v531 as _latest
finally:
    _sys.modules["scanner"] = _wrapper

app = _latest.app
RUNTIME_VERSION = "5.3.1"


# Navigation-only backlink; applying/deploying this patch needs separate approval.
@app.after_request
def rotation_staging_backlink(response):
    from flask import request
    if (request.path in ('/', '/scanner', '/analysis') and response.status_code == 200
            and response.mimetype == 'text/html' and not response.direct_passthrough):
        body = response.get_data(as_text=True)
        if 'id="rotation-staging-backlink"' not in body:
            link = ('<nav id="rotation-staging-backlink" aria-label="Rotation Staging" '
                    'style="padding:12px;background:#0d1b2a">'
                    '<a href="https://ai-market-radar-rotation-staging.onrender.com/rotation" '
                    'style="display:inline-flex;align-items:center;min-height:44px;color:#b9deff">'
                    'Capital Rotation (Staging) →</a></nav>')
            response.set_data(body.replace('<body>', '<body>'+link, 1))
    return response
