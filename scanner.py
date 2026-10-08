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
