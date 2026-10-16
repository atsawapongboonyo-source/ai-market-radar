"""Offline Gunicorn worker lifecycle smoke, no market-data endpoints.

Run with safe flags and diagnostics disabled; verify workers boot, answer a
read-only monitor endpoint, and survive repeated short-lived connections.
"""
import os
import subprocess
import sys
import time
import urllib.request

for key in ("SERVER_AUTO_MONITOR_ENABLED", "TELEGRAM_TEST_ON_BOOT", "LIVE_TRADING"):
    assert os.environ.get(key) == "0", key

port = 18743
cmd = [sys.executable, "-m", "gunicorn", "scanner:app", "--bind",
       f"127.0.0.1:{port}", "--workers", "2", "--timeout", "20",
       "--access-logfile", "-", "--error-logfile", "-"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, env=os.environ.copy())
try:
    ready = False
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError(f"Gunicorn exited prematurely: {proc.returncode}")
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/server-monitor-status", timeout=2
            ) as response:
                assert response.status == 200
                ready = True
                break
        except (OSError, TimeoutError):
            time.sleep(0.25)
    assert ready, "Gunicorn did not become ready"
    for _ in range(20):
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/server-monitor-status", timeout=4
        ) as response:
            assert response.status == 200
            assert b'"ok"' in response.read()
    assert proc.poll() is None, "Gunicorn exited during read-only requests"
    print("GUNICORN_WORKER_LIFECYCLE_OK workers=2 requests=20", flush=True)
finally:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=5)
    print(out[-4000:])
