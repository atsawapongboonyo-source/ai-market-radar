"""Offline-only correlation of Gunicorn crash, request and metric evidence.

A nearby request is not proof that it caused a native crash.
No runtime hooks, network access or trading behavior.
"""
from datetime import datetime, timezone
import re

_CRASH = re.compile(r"Worker \(pid:(\d+)\) was sent code (\d+)!")
_TIMEOUT = re.compile(r"WORKER TIMEOUT.*pid:(\d+)")
_REQUEST = re.compile(r"(/api/[A-Za-z0-9_/-]+)")


def _utc(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("invalid timestamp")
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


def correlate_crashes(app_logs, request_logs, window_seconds=30):
    """Return evidence around crashes, never claim request causation."""
    if not isinstance(window_seconds, (int, float)) or not 0 <= window_seconds <= 300:
        raise ValueError("invalid window")
    crashes = []
    for entry in app_logs:
        message = entry.get("message", "")
        match = _CRASH.search(message)
        if not match:
            continue
        when = _utc(entry["timestamp"])
        nearby = []
        for request in request_logs:
            delta = (_utc(request["timestamp"]) - when).total_seconds()
            if abs(delta) > window_seconds:
                continue
            path = request.get("path")
            if not isinstance(path, str):
                match_path = _REQUEST.search(request.get("message", ""))
                path = match_path.group(1) if match_path else None
            if path and path.startswith("/api/"):
                nearby.append({"path": path, "offset_seconds": round(delta, 3),
                               "status": request.get("statusCode")})
        crashes.append({"at_utc": when.isoformat(), "pid": int(match.group(1)),
                        "exit_code": int(match.group(2)), "nearby_requests": nearby,
                        "root_cause": "UNDETERMINED"})
    return crashes


def summarize_timeout_events(app_logs):
    result = []
    for entry in app_logs:
        match = _TIMEOUT.search(entry.get("message", ""))
        if match:
            result.append({"at_utc": _utc(entry["timestamp"]).isoformat(),
                           "pid": int(match.group(1)), "type": "WORKER_TIMEOUT"})
    return result
