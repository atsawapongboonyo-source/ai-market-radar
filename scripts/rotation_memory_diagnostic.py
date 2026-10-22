"""Offline diagnostic in a credential-free child; never imports a live entrypoint.

Measures imports and the existing isolation probe, then demonstrates retained
history-cache objects using bounded synthetic OHLCV. Not a Render acceptance test.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def child(output):
    import gc
    import importlib
    import platform
    import runpy
    import threading
    from unittest.mock import patch
    import psutil

    # Fail before network/process side effects, including during scanner import.
    denied = []
    def audit(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
            denied.append(event)
            raise RuntimeError('OFFLINE_DIAGNOSTIC_SIDE_EFFECT_BLOCKED')
    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT))
    proc = psutil.Process()
    stop = threading.Event()
    peak = [proc.memory_info().rss]
    samples = []
    def sample():
        peak[0] = max(peak[0], proc.memory_info().rss)
    def checkpoint(phase, **extra):
        sample()
        samples.append(dict(phase=phase, rss_mib=round(proc.memory_info().rss / 2**20, 3), **extra))
    def monitor():
        while not stop.wait(.01):
            sample()
    sampler = threading.Thread(target=monitor, name='offline-rss-sampler', daemon=True)
    sampler.start()
    try:
        checkpoint('python_and_psutil')
        for name in ('flask', 'pandas', 'yfinance', 'scanner'):
            importlib.import_module(name)
            checkpoint(name + '_imported')
        threads = threading.active_count()
        with tempfile.TemporaryDirectory() as directory:
            old_argv = sys.argv
            try:
                sys.argv = ['rotation_web_probe.py', '--output', str(Path(directory) / 'rotation.json')]
                runpy.run_path(str(ROOT / 'scripts' / 'rotation_web_probe.py'), run_name='__main__')
            finally:
                sys.argv = old_argv
            rotation = json.loads((Path(directory) / 'rotation.json').read_text())
        checkpoint('rotation_probe_completed')

        # Exercise the real cache insertion path, never the scanner engine or API.
        import app as core
        import pandas as pd
        assert not core._HISTORY_CACHE, 'Use a fresh child process'
        frame = pd.DataFrame({name: [float(i + 1) for i in range(1260)]
                              for name in ('Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume')},
                             index=pd.date_range('2020-01-01', periods=1260))
        def cache_stats():
            return dict(cache_entries=len(core._HISTORY_CACHE),
                        cache_frame_bytes=sum(int(v[1].memory_usage(index=True, deep=True).sum())
                                              for v in core._HISTORY_CACHE.values()))
        checkpoint('history_cache_empty', **cache_stats())
        with patch.object(core.yf, 'download', side_effect=lambda *a, **k: frame.copy()) as download:
            for i in range(256):
                core.download_history('SYNTH%03d' % i, period='5y')
                if i + 1 in (64, 128, 256):
                    checkpoint('synthetic_history_' + str(i + 1), **cache_stats())
                    assert cache_stats()['cache_entries'] <= 128
                    assert cache_stats()['cache_frame_bytes'] <= 8 * 2**20
            # Advance the process clock to inspect expiry of unrelated keys.
            with patch.object(core.time, 'time', return_value=10**12):
                core.download_history('SYNTH_NEW', period='5y')
                gc.collect()
                retained = cache_stats()
                checkpoint('expired_history_after_gc', **retained)
                assert retained['cache_entries'] == 1, retained
            calls = download.call_count
        core._HISTORY_CACHE.clear()
        gc.collect()
        checkpoint('history_cache_cleared', **cache_stats())
        assert threading.active_count() == threads, 'Unexpected background thread'
        assert not denied, denied
        result = dict(simulation_only=True, python=platform.python_version(),
                      platform=platform.system(), sampled_interval_ms=10,
                      rss_sampled_peak_mib=round(peak[0] / 2**20, 3),
                      rss_samples=samples, rotation_probe=rotation,
                      synthetic_download_calls=calls, expired_cache=retained,
                      blocked_side_effect_attempts=len(denied),
                      limitations=['Single process; excludes Gunicorn master and container page cache',
                                   'Synthetic history; no live provider/native allocation profile',
                                   '10ms sampling may miss shorter peaks; no live root-cause attribution'])
    finally:
        stop.set()
        sampler.join(timeout=2)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args.output.resolve())
        return
    # Do not inherit database URLs, provider/Telegram keys, monitor settings or PYTHONPATH.
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'TMPDIR', 'HOME',
               'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(TELEGRAM_TEST_ON_BOOT='0', SERVER_AUTO_MONITOR_ENABLED='0', PYTHONDONTWRITEBYTECODE='1')
    output = args.output.resolve()
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', '--output', str(output)],
                       cwd=directory, env=env, check=True, timeout=120)


if __name__ == '__main__':
    main()
