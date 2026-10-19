"""Offline Gunicorn worker lifecycle smoke, no market-data endpoints.

Run with safe flags and diagnostics disabled; verify workers boot, answer a
read-only monitor endpoint, and survive repeated short-lived connections.
"""
import os
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time
import urllib.request

for key in ("TELEGRAM_TEST_ON_BOOT", "LIVE_TRADING"):
    assert os.environ.get(key) == "0", key
monitor_flag = os.environ.get("SERVER_AUTO_MONITOR_ENABLED")
if monitor_flag == "1":
    # Only permit monitor-enabled mode when the CI-only startup shim is present.
    import sitecustomize
    assert sitecustomize.__file__.startswith("/workspace/ci_monitor_stub/"), "unsafe monitor startup"
else:
    assert monitor_flag == "0", "unsafe monitor startup"

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
    if os.environ.get("RADAR_BOUNDED_LOAD") == "1":
        # Offline-only read-only concurrency gate; no external market calls.
        def fetch_status(_):
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/server-monitor-status", timeout=6
            ) as response:
                payload = response.read()
                assert response.status == 200 and b'"ok"' in payload
                return len(payload)
        with ThreadPoolExecutor(max_workers=4) as pool:
            lengths = list(pool.map(fetch_status, range(80)))
        assert len(lengths) == 80 and all(n > 0 for n in lengths)
        assert proc.poll() is None, "Gunicorn exited during concurrent requests"
        # Read current resident memory for master + direct worker processes.
        def rss_kib(pid):
            with open(f"/proc/{pid}/status", encoding="utf-8") as status:
                for line in status:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
            raise AssertionError("VmRSS missing")
        with open(f"/proc/{proc.pid}/task/{proc.pid}/children", encoding="utf-8") as children:
            worker_pids = [int(p) for p in children.read().split()]
        assert len(worker_pids) == 2, f"expected 2 live workers, found {worker_pids}"
        rss_total = sum(rss_kib(pid) for pid in [proc.pid, *worker_pids])
        print(f"BOUNDED_OFFLINE_LOAD_OK requests=80 concurrency=4 rss_snapshot_kib={rss_total}", flush=True)
        # cgroup v2 memory.peak records high-water memory since container start,
        # unlike a point-in-time RSS snapshot. OOM counters catch transient kills.
        peak_path = "/sys/fs/cgroup/memory.peak"
        events_path = "/sys/fs/cgroup/memory.events"
        if os.path.isfile(peak_path) and os.path.isfile(events_path):
            with open(peak_path, encoding="utf-8") as handle:
                peak_bytes = int(handle.read().strip())
            with open(events_path, encoding="utf-8") as handle:
                events = dict(line.split() for line in handle)
            oom = int(events.get("oom", "0"))
            oom_kill = int(events.get("oom_kill", "0"))
            print(f"CGROUP_MEMORY_PEAK_BYTES={peak_bytes} OOM={oom} OOM_KILL={oom_kill}", flush=True)
            assert peak_bytes > 0, "missing memory peak"
            assert oom == 0 and oom_kill == 0, "cgroup memory exhaustion detected"
        else:
            print("CGROUP_MEMORY_PEAK_UNAVAILABLE: cgroup v2 memory files absent", flush=True)
    print("GUNICORN_WORKER_LIFECYCLE_OK workers=2 requests=20", flush=True)
finally:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=5)
    print(out[-4000:])
