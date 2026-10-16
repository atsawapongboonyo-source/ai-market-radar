"""Offline native dependency audit; no network, market calls, or trading.

Prints versions and extension module origins for reproducibility. A successful
import is not evidence that a SIGSEGV cannot occur under production load.
"""
import importlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

assert os.environ.get("SERVER_AUTO_MONITOR_ENABLED") == "0"
assert os.environ.get("TELEGRAM_TEST_ON_BOOT") == "0"
assert os.environ.get("LIVE_TRADING") == "0"

packages = ("numpy", "pandas", "yfinance", "curl_cffi", "lxml", "multitasking",
            "requests", "flask", "gunicorn", "peewee", "frozendict")
inventory = {}
for name in packages:
    try:
        version = importlib.metadata.version(name.replace("_", "-"))
    except importlib.metadata.PackageNotFoundError:
        version = "NOT_INSTALLED"
    inventory[name] = {"version": version}

for name in ("numpy", "pandas", "yfinance", "curl_cffi", "lxml"):
    if inventory[name]["version"] == "NOT_INSTALLED":
        inventory[name]["import_status"] = "NOT_INSTALLED"
        continue
    module = importlib.import_module(name)
    inventory[name]["import_status"] = "OK"
    inventory[name]["origin"] = str(getattr(module, "__file__", "UNKNOWN"))
    inventory[name]["native_extension_count"] = sum(
        1 for item in sys.modules.values()
        if str(getattr(item, "__file__", "")).endswith((".so", ".pyd"))
    )

print(json.dumps({"python": sys.version.split()[0], "packages": inventory},
                 indent=2, sort_keys=True))
print("OFFLINE_NATIVE_DEPENDENCY_AUDIT_OK")
