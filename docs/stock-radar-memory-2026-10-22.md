# Stock Radar V2 memory investigation — HOLD

Continuation of Draft PR #21 at 1a1e9fb7bca7905516ba6ff53ac9412f439e6689.
Measured 2026-10-22, Windows 10, Python 3.12.14, 16 GiB host.
All changes are on feature/stock-radar-v2-universe-audit. No deploy or restart.

## Findings and scope

The shared core app retained every distinct (ticker, period) history frame in a
plain dictionary. TTL prevented stale hits but never evicted unrelated expired
entries. A synthetic 256-symbol, 1260-row OHLCV run through the real
download_history insertion path retained 257 frames / 18,133,920 accounted bytes
after advancing the clock. This demonstrates a retention defect, not the complete
cause of Render's container memory usage.

HistoryCache now limits retained DataFrame accounting to 8 MiB and 128 entries,
evicts least recently used entries, and releases expired entries on cache access.
Oversized frames are returned normally but not cached. A lock protects cache
bookkeeping across request threads. The cache continues returning the original
tuple shape; download_history still copies hits and stored frames. No indicator,
execution, position, scanner route, or Scanner V4.10 source was edited. app.py is
shared by Scanner, so eviction can increase provider calls for working sets above
the budget; offline validation does not establish production latency/rate limits.
The bound covers accounted frame bytes, not total RSS, Python metadata, in-flight
downloads/copies, other module caches, or native allocations. Idle expiry occurs
on the next access, without a cleanup thread.

## Measured Windows results

Artifacts: memory-evidence/windows-before.json and windows-after.json.
Separate fresh processes: RSS varies between runs; cache bytes/counts are the
stronger controlled evidence. Synthetic values are never market quotes/signals.

| Phase | Before RSS MiB | After RSS MiB |
|---|---:|---:|
| Python + diagnostic dependencies | 24.734 | 24.625 |
| Flask imported | 35.645 | 35.625 |
| pandas imported | 74.629 | 74.391 |
| yfinance imported | 89.816 | 89.887 |
| Scanner imported | 90.461 | 90.504 |
| Rotation isolation probe completed | 99.559 | 99.234 |
| 256 synthetic history requests | 115.652 | 106.129 |
| Expired history after GC | 115.742 | 99.719 |
| 10ms sampled whole-run peak | 115.742 | 106.129 |

Before: 257 retained expired/new frames, 18,133,920 bytes (~17.294 MiB).
After: plateau at 118 frames, 8,326,080 bytes (~7.940 MiB); expiry leaves
one fresh frame, 70,560 bytes. Sampled peak is ~9.61 MiB lower in these runs.
The diagnostic child inherits no provider/database/Telegram settings, disables
boot notifications and the server monitor, uses a temporary working directory,
and denies Python socket/process audit events. Both runs recorded zero blocked
side-effect attempts. Only synthetic history was downloaded from the stub.

The existing isolation probe reads Rotation 1500 times and blocked opportunities
500 times. In the after run its RSS checkpoints were: Scanner/test imports
92.387, initialized 93.754, signed ingest 95.133, Rotation 100/500/1000/1500 reads
95.289/95.371/95.383/95.395, Home 99.230, opportunities 99.230, after GC 99.230 MiB.
No market downloads, new application threads, scanner function replacements or
position-output differences were observed. The RSS sampler is diagnostic only.

## CI and local validation

Exact starting head CI was successful:
- Research universe: Actions run 39759370725, Windows + Linux.
- Web isolation: run 39759370850; Windows 172 passed/22 skipped, Linux
  169 passed/25 skipped; PostgreSQL and mobile/navigation jobs passed.
- Original CI Rotation probe peak: Windows 105.980 MiB; Linux 133.719 MiB.

Local baseline: 172 passed/22 skipped. After cache change: 176 passed/22 skipped;
subsequently all five focused cache tests passed, including concurrent insertion.
PostgreSQL skips are not acceptance evidence for a live database.
The PR workflow now executes the diagnostic on Windows/Linux, asserts frame
retention limits and expiry, and uploads both memory JSON files on both OSes.
Exact updated-head CI must be checked after push.

## Render observations and blockers

Read-only discovery re-confirmed workspace tea-dacd3c0ae00c73euru00 and service
srv-dbbo8gs9v7es73fskc0g, one free instance, autoDeploy=no/trigger=off, configured
branch feature/rotation-stock-decision-v1. Live deploy remains
dep-dbcc8u8m7kps73a70n50 at 96f3000588bd11cd069d91a7402d34fb5651b58d,
not PR #21. Start command has one Gunicorn worker and two threads.

300-second service memory samples on instance h7nb9: 465,399,800 bytes at
09:35Z (~443.840 MiB), 481,554,430 at 09:45Z (~459.246 MiB),
503,111,680 at 09:50Z (~479.805 MiB), and 503,119,870 at 11:40Z
(~479.813 MiB, 93.71% of 512 MiB). These are container/service metrics,
not single-process RSS; 300-second sampling can miss shorter peaks.

The complete 09:40–09:55Z app-log query (hasMore=false) contains mobile Home,
multi-radar, repeated scan calls, top-picks, history-analysis NVDA/MU/MRVL,
theme leaders, catalyst calls and monitor-status polling during the increase.
The 09:51Z signed Rotation ingest followed the observed 09:50Z plateau.
This supports investigating the shared Scanner/provider/cache path; it does not
prove a particular route's allocation or exclude earlier ingest/provider/native
effects. Recent logs also show yfinance activity. No live load probe was run.

HOLD: memory budget remains exceeded by the currently deployed code. No on-host
Render per-process profile, real-provider allocation/concurrency replay, or
candidate live soak has been performed. Windows Python 3.12 measurements cannot
be substituted for Render's Python 3.14/container/Gunicorn measurements.
Physical DB free/used/WAL evidence, stock-complete recovery drill, pinned rollback
and return-to-current drill, signed-ingest/restart persistence, and live Scanner
isolation remain unverified gates from the prior audit; no new evidence marks
them passed. Do not deploy Staging until RAM/storage/rollback/restart gates pass.
No merge, Production changes, trading, new services or paid resources authorized.
