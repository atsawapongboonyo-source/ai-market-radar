"""Opt-in, read-only WSGI request lifecycle diagnostics.

Enable only after review via RADAR_REQUEST_DIAGNOSTICS=1.
Logs endpoint template (never query strings, bodies, headers or credentials).
Does not catch native crashes: a missing END after START is only a clue.
"""
import logging
import os
import re
import time
import uuid

_ALLOWED = re.compile(r"^[A-Za-z0-9_./<>:-]{1,160}$")
_LOG = logging.getLogger("gunicorn.error")


def safe_path(environ):
    """Prefer Flask/Werkzeug route template to avoid logging personal path values."""
    template = environ.get("radar.route_template")
    if isinstance(template, str) and _ALLOWED.fullmatch(template):
        return template
    return "UNMAPPED"


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

        def stream():
            try:
                yield from iterable
            except BaseException:
                self.emit("REQUEST_STREAM_EXCEPTION id=%s pid=%d elapsed_ms=%d",
                          request_id, pid, int((self.clock() - started) * 1000))
                raise
            finally:
                close = getattr(iterable, "close", None)
                try:
                    if close is not None:
                        close()
                finally:
                    self.emit("REQUEST_END id=%s pid=%d route=%s status=%s elapsed_ms=%d",
                              request_id, pid, safe_path(environ), status,
                              int((self.clock() - started) * 1000))
        return stream()
