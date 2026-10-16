"""Read-only Gunicorn worker crash diagnostics.

This opt-in module does not start workers, fetch market data, or alter trading.
Run with: python -m unittest -v test_worker_crash_diagnostics
"""
import re

_CRASH = re.compile(r"Worker \(pid:(\d+)\) was sent code (\d+)!")
_BOOT = re.compile(r"Booting worker with pid: (\d+)")
_TIMEOUT = re.compile(r"WORKER TIMEOUT.*pid:(\d+)")


def summarize_worker_logs(lines):
    """Parse a bounded list of log messages without storing user identifiers."""
    result = {"crashes": [], "boots": [], "timeouts": [], "unknown": 0}
    for line in lines:
        if not isinstance(line, str):
            result["unknown"] += 1
            continue
        crash = _CRASH.search(line)
        boot = _BOOT.search(line)
        timeout = _TIMEOUT.search(line)
        if crash:
            code = int(crash.group(2))
            result["crashes"].append({
                "pid": int(crash.group(1)), "exit_code": code,
                "signal": code - 128 if 129 <= code <= 192 else None,
            })
        elif boot:
            result["boots"].append(int(boot.group(1)))
        elif timeout:
            result["timeouts"].append(int(timeout.group(1)))
    return result


def assess_memory(samples_bytes, limit_bytes):
    """Return a point-in-time memory summary; not proof of crash root cause."""
    if not isinstance(limit_bytes, (int, float)) or limit_bytes <= 0:
        return {"status": "INSUFFICIENT_DATA"}
    samples = [x for x in samples_bytes if isinstance(x, (int, float)) and x >= 0]
    if not samples:
        return {"status": "INSUFFICIENT_DATA"}
    peak = max(samples)
    return {"status": "SAMPLED", "peak_bytes": peak,
            "limit_bytes": limit_bytes, "peak_fraction": peak / limit_bytes,
            "caveat": "Sampling may miss transient memory spikes."}
