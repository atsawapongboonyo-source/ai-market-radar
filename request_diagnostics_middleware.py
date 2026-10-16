"""Opt-in, read-only WSGI request lifecycle diagnostics.

Enable only after review via RADAR_REQUEST_DIAGNOSTICS=1.
Logs endpoint template (never query strings, bodies, headers or credentials).
Does not catch native crashes: a missing END after START is only a clue.
"""
import logging
import os
import time
import uuid
from werkzeug.wsgi import ClosingIterator

_LOG = logging.getLogger("gunicorn.error")

# Explicit, fixed route templates only. Do not emit arbitrary Flask route
# patterns: literal segments may contain tenant names or other sensitive data.
_SAFE_ROUTES = frozenset({
    "/api/scan", "/api/top-picks", "/api/theme-rotation",
    "/api/multi-radar", "/api/server-monitor-status",
    "/api/catalyst/<ticker>",
})


def safe_path(environ):
    """Return an approved route template; never include user-supplied paths."""
    template = environ.get("radar.route_template")
    return template if isinstance(template, str) and template in _SAFE_ROUTES else "UNMAPPED"


class RequestDiagnosticsMiddleware:
    def __init__(self, app, enabled=False, clock=None, emit=None):
        self.app = app
        self.enabled = enabled
        self.clock = clock or time.monotonic
        self.emit = emit or _LOG.info

    def __call__(self, environ, start_response):
        if not self.enabled:
            return self.app(environ, start_response)
        request_id = uuid.uuid4().hex[:12]
        started = self.clock()
        pid = os.getpid()
        path = safe_path(environ)
        self.emit("REQUEST_START id=%s pid=%d route=%s", request_id, pid, path)
        status = "UNKNOWN"
        def wrapped_start_response(status_line, headers, exc_info=None):
            nonlocal status
            status = str(status_line).split(" ", 1)[0]
            return start_response(status_line, headers, exc_info)
        try:
            iterable = self.app(environ, wrapped_start_response)
        except BaseException:
            self.emit("REQUEST_EXCEPTION id=%s pid=%d elapsed_ms=%d",
                      request_id, pid, int((self.clock() - started) * 1000))
            raise

        completed = False
        def finish():
            nonlocal completed
            if completed:
                return
            completed = True
            self.emit("REQUEST_END id=%s pid=%d route=%s status=%s elapsed_ms=%d",
                      request_id, pid, safe_path(environ), status,
                      int((self.clock() - started) * 1000))

        original_closed = False
        def close_original_once():
            nonlocal original_closed
            if original_closed:
                return
            original_closed = True
            close = getattr(iterable, "close", None)
            if close is not None:
                close()

        def stream():
            try:
                yield from iterable
            except BaseException:
                self.emit("REQUEST_STREAM_EXCEPTION id=%s pid=%d elapsed_ms=%d",
                          request_id, pid, int((self.clock() - started) * 1000))
                raise
            finally:
                try:
                    close_original_once()
                finally:
                    finish()
        return ClosingIterator(stream(), [close_original_once, finish])
