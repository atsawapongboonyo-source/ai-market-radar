"""Repeat isolated native imports without network or broker access."""
import importlib
import os
import subprocess
import sys

for flag in ("SERVER_AUTO_MONITOR_ENABLED", "TELEGRAM_TEST_ON_BOOT", "LIVE_TRADING"):
    assert os.environ.get(flag) == "0", flag

modules = ("numpy", "pandas", "curl_cffi", "yfinance")
for attempt in range(10):
    code = ("import importlib\n" +
            "for name in " + repr(modules) + ": importlib.import_module(name)\n" +
            "print('NATIVE_IMPORT_CHILD_OK')\n")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=25, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode:
        raise RuntimeError(
            f"native import iteration {attempt + 1} failed: "
            f"returncode={result.returncode}; stderr={result.stderr[-2000:]}"
        )
    print(f"native import iteration {attempt + 1}/10 OK", flush=True)
print("NATIVE_IMPORT_REPETITION_OK")
