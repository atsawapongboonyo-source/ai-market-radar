"""Offline diagnostic in credential-free disposable processes.

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


def clean_environment():
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'TMPDIR', 'HOME',
               'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(TELEGRAM_TEST_ON_BOOT='0', SERVER_AUTO_MONITOR_ENABLED='0', PYTHONDONTWRITEBYTECODE='1')
    return env


def gunicorn_startup(output):
    """Linux only: actual entrypoint, temporary SQLite, zero HTTP/provider traffic."""
    import time
    import psutil
    if sys.platform != 'linux':
        raise RuntimeError('Gunicorn startup measurement requires Linux')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / 'offline_config.py'
        config.write_text(
            'import sys\n'
            'def deny(event, args):\n'
            "    if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):\n"
            "        raise RuntimeError('OFFLINE_STARTUP_SIDE_EFFECT_BLOCKED')\n"
            'sys.addaudithook(deny)\n', encoding='utf-8')
        env = clean_environment()
        env['ROTATION_STAGING_DATA_DIR'] = directory
        samples = []
        with (root / 'startup.log').open('w+', encoding='utf-8') as log:
            process = subprocess.Popen(
                [sys.executable, '-m', 'gunicorn', '--config', str(config),
                 '--chdir', str(ROOT), '--bind', '127.0.0.1:0',
                 '--workers', '1', '--threads', '2', '--timeout', '60', 'rotation_staging:app'],
                env=env, cwd=directory, stdout=log, stderr=subprocess.STDOUT)
            try:
                started = time.monotonic()
                while time.monotonic() - started < 30:
                    if process.poll() is not None:
                        raise RuntimeError('Disposable Gunicorn exited before observation completed')
                    processes = [psutil.Process(process.pid)]
                    processes += processes[0].children(recursive=True)
                    memory = [p.memory_full_info() for p in processes]
                    samples.append(dict(seconds=round(time.monotonic()-started, 3),
                                        processes=len(processes),
                                        rss_mib=sum(m.rss for m in memory)/2**20,
                                        pss_mib=sum(m.pss for m in memory)/2**20))
                    time.sleep(.1)
                log.flush()
                log.seek(0)
                logs = log.read()
                assert 'Booting worker' in logs and 'ERROR' not in logs, 'Startup failed'
                assert 'OFFLINE_STARTUP_SIDE_EFFECT_BLOCKED' not in logs, 'Unexpected side effect'
                assert samples[-1]['processes'] == 2, samples[-1]
                assert (root / 'rotation-staging.sqlite').exists(), 'Disposable store missing'
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        result = dict(simulation_only=True, mode='gunicorn_startup', python=sys.version.split()[0],
                      workers=1, configured_threads=2, seconds=30, http_requests=0,
                      storage='temporary SQLite, no live database credentials',
                      peak_summed_rss_mib=round(max(x['rss_mib'] for x in samples), 3),
                      peak_summed_pss_mib=round(max(x['pss_mib'] for x in samples), 3),
                      final=samples[-1],
                      limitations=['Startup only, no representative load or PostgreSQL',
                                   'Summed RSS double-counts shared pages; PSS apportions them',
                                   'Not Render container memory or a 400 MiB acceptance result'])
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))


def child(output, cache_mode='bounded', cycle_count=3):
    import gc
    import importlib
    import runpy
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from importlib.metadata import version, PackageNotFoundError
    from unittest.mock import patch
    import psutil

    # Fail before network/process side effects, including during scanner import.
    denied = []
    def dependency_version(name):
        try:
            return version(name)
        except PackageNotFoundError:
            return None
    def audit(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
            denied.append(event)
            raise RuntimeError('OFFLINE_DIAGNOSTIC_SIDE_EFFECT_BLOCKED')
    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT))
    proc = psutil.Process()
    started = time.monotonic()
    stop = threading.Event()
    peak = [proc.memory_info().rss]
    samples = []
    def sample():
        peak[0] = max(peak[0], proc.memory_info().rss)
    def checkpoint(phase, **extra):
        sample()
        samples.append(dict(phase=phase, rss_mib=round(proc.memory_info().rss / 2**20, 3),
                            os_threads=proc.num_threads(), python_threads=threading.active_count(), **extra))
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
        # Recreate the deployed pre-fix container only in this disposable child.
        if cache_mode == 'unbounded':
            core._HISTORY_CACHE = {}
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
                    if cache_mode == 'bounded':
                        assert cache_stats()['cache_entries'] <= 128
                        assert cache_stats()['cache_frame_bytes'] <= 8 * 2**20
            # Advance the process clock to inspect expiry of unrelated keys.
            with patch.object(core.time, 'time', return_value=10**12):
                core.download_history('SYNTH_NEW', period='5y')
                gc.collect()
                retained = cache_stats()
                checkpoint('expired_history_after_gc', **retained)
                assert retained['cache_entries'] == (1 if cache_mode == 'bounded' else 257), retained
            calls = download.call_count
        core._HISTORY_CACHE.clear()
        gc.collect()
        checkpoint('history_cache_cleared', **cache_stats())
        # Two callers match the configured Gunicorn thread count. Exercise real
        # cache copies and eviction, but replace provider I/O with bounded data.
        # Never retain all returned frames in the executor's result collection.
        def request(i):
            result = core.download_history('CYCLE%03d' % i, period='5y')
            assert len(result) == len(frame)
            return len(result)
        cycles = []
        with patch.object(core.yf, 'download', side_effect=lambda *a, **k: frame.copy()) as provider:
            for cycle in range(cycle_count):
                core._HISTORY_CACHE.clear()
                for i in range(64):
                    request(i)
                cold_calls = provider.call_count
                for i in range(64):
                    request(i)
                assert provider.call_count == cold_calls, 'Warm cache unexpectedly downloaded'
                with ThreadPoolExecutor(max_workers=2) as pool:
                    assert sum(pool.map(request, range(64, 320))) == 256 * len(frame)
                stats = cache_stats()
                if cache_mode == 'bounded':
                    assert stats['cache_entries'] <= 128 and stats['cache_frame_bytes'] <= 8 * 2**20
                checkpoint('concurrent_cycle_%d' % cycle, **stats)
                core._HISTORY_CACHE.clear()
                gc.collect()
                checkpoint('cycle_%d_cleared_after_gc' % cycle, **cache_stats())
                cycles.append(dict(cycle=cycle, cumulative_synthetic_provider_calls=provider.call_count))
            # Increasing unique-key sweep exposes retained old-cache growth,
            # rather than repeatedly measuring only the same small warm set.
            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sum(pool.map(request, range(1024))) == 1024 * len(frame)
            sweep = cache_stats()
            checkpoint('unique_1024_retained', **sweep)
            if cache_mode == 'bounded':
                assert sweep['cache_entries'] <= 128 and sweep['cache_frame_bytes'] <= 8 * 2**20
            else:
                assert sweep['cache_entries'] == 1024
            core._HISTORY_CACHE.clear()
            gc.collect()
            checkpoint('unique_sweep_cleared_after_gc', **cache_stats())
        assert threading.active_count() == threads, 'Unexpected background thread'
        assert not denied, denied
        # platform.system() can spawn `ver` on older Windows Python releases.
        result = dict(simulation_only=True, python=sys.version.split()[0],
                      cache_mode=cache_mode, elapsed_seconds=round(time.monotonic()-started, 3),
                      unique_sweep=sweep,
                      platform={'win32': 'Windows', 'linux': 'Linux'}.get(sys.platform, sys.platform),
                      sampled_interval_ms=10,
                      rss_sampled_peak_mib=round(peak[0] / 2**20, 3),
                      rss_samples=samples, rotation_probe=rotation,
                      synthetic_download_calls=calls, expired_cache=retained,
                      concurrent_workers=2, repeated_cycles=cycles,
                      dependencies={name: dependency_version(name) for name in
                                    ('Flask', 'gunicorn', 'pandas', 'numpy', 'yfinance',
                                     'curl_cffi', 'cryptography', 'psycopg', 'psutil')},
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
    parser.add_argument('--cache-mode', choices=('bounded', 'unbounded'), default='bounded')
    parser.add_argument('--cycles', type=int, choices=range(1, 61), default=3, metavar='1..60')
    parser.add_argument('--gunicorn-startup', action='store_true')
    args = parser.parse_args()
    if args.gunicorn_startup:
        gunicorn_startup(args.output.resolve())
        return
    if args.child:
        child(args.output.resolve(), args.cache_mode, args.cycles)
        return
    # Do not inherit database URLs, provider/Telegram keys, monitor settings or PYTHONPATH.
    env = clean_environment()
    output = args.output.resolve()
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', '--output', str(output),
                        '--cache-mode', args.cache_mode, '--cycles', str(args.cycles)],
                       cwd=directory, env=env, check=True, timeout=240)


if __name__ == '__main__':
    main()
