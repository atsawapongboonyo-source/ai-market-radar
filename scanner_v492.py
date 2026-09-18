"""AI MARKET RADAR V4.9.2 compatibility layer.

V5.0 owns HTML presentation. This module now preserves only the no-cache
behavior required by the live scanner UI; V4.9.2 legacy finalizers and route
HTML injectors are intentionally disabled. Scanner/Top Pick/Opening/Position
logic is unchanged in their owning modules.
"""

import scanner_v491 as v491

app = v491.app

@app.after_request
def _v492_no_cache(response):
    try:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    except Exception:
        pass
    return response
