"""Bounded offline concurrent native computation smoke test.

No market data, broker calls, HTTP or production process interaction.
This test is diagnostic only and cannot prove production crash remediation.
"""
import concurrent.futures
import os
import numpy as np
import pandas as pd

for key in ("SERVER_AUTO_MONITOR_ENABLED", "TELEGRAM_TEST_ON_BOOT", "LIVE_TRADING"):
    assert os.environ.get(key) == "0", key

def compute(seed):
    data = np.arange(2000, dtype=np.float64) + seed
    series = pd.Series(data)
    moving = series.rolling(20, min_periods=20).mean()
    assert np.isfinite(moving.iloc[-1])
    return float(moving.iloc[-1])

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    values = list(pool.map(compute, range(40)))
assert len(values) == 40
assert all(np.isfinite(value) for value in values)
print("NATIVE_CONCURRENT_COMPUTE_OK tasks=40 workers=4")
