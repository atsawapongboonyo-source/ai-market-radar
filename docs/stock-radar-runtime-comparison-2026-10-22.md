# Runtime comparison — Staging HOLD

## Cache A/B and SIGKILL follow-up

Exact c3e527a GitHub head and both workflows rechecked: research 39788788826 and
web 39788788893 succeeded, including all four integration jobs and PostgreSQL.
Staging config remains auto-deploy off, one worker/two threads/60s timeout;
live deploy 96f3000 and historical rollback target 9be467f unchanged.

30-second Render samples show 536,539,140 bytes (511.684 MiB) at 20:36:30
Bangkok, against 536,870,900 bytes, only 0.316 MiB headroom (99.938% used).
Worker 66 SIGKILL was logged at 20:36:28.666; worker 2847 booted .097s later.
At 20:37 metric fell to 272,166,900 bytes (259.559 MiB). Sampling cannot prove
the instantaneous peak or whether the 20:36:30 point contains startup overlap.
Logs for 20:34–20:37 returned hasMore=false with no WORKER TIMEOUT message.
Gunicorn 23.0.0 installed source logs WORKER TIMEOUT before SIGABRT, escalating
to SIGKILL later; it appends 'Perhaps out of memory?' for any SIGKILL. Therefore
memory pressure/OOM is strongly supported, timeout is unsupported by these logs,
but kernel/cgroup OOM evidence is still missing. Events returned empty.

Extended the existing diagnostic rather than creating a separate probe. Both
cache modes run in distinct credential-free children against identical synthetic
histories: 30 cold/warm/concurrent cycles, followed by 1,024 unique keys. The
unbounded mode substitutes the old dictionary only in the disposable process.
Bounded mode asserts the 8 MiB/128 cap, old mode asserts retained key counts;
warm-cache reads must not add synthetic provider calls. No Scanner logic changes.

Fresh local Windows Python 3.12.14: bounded peak 120.191 MiB versus unbounded
183.145 MiB, a 62.954 MiB reduction for this workload. Unique sweep retention:
8,326,080 bytes /118 frames versus 72,253,440 bytes /1,024 frames, reducing
accounted retention by 63,927,360 bytes. Elapsed 17.641s/14.875s respectively;
this is a short synthetic stress comparison, not a continuous Render soak.
Fresh regressions: 177 passed/22 skipped. Missing local PostgreSQL is not passed.

Linux CI now also measures the actual Gunicorn entrypoint with 1 worker/2 threads
for 30 seconds, using disposable localhost PostgreSQL and scrubbed env. The first
harness attempt used SQLite and correctly failed POSTGRES_REQUIRED; no application
requirement was relaxed. Python network/process auditing permits only the local
disposable database address, before worker imports; no HTTP requests are sent.
The guard is not a native-library network sandbox. Reports summed RSS and PSS
(RSS double-counts shared pages). Startup evidence excludes live PostgreSQL,
real provider load and container cache. Both Python runtimes use observed build
dependency constraints. Independent CI jobs are no longer cancelled on one failure.
CI also fingerprints all baseline/stock/nonce/schema rows before and after
restarting only its disposable PostgreSQL container, verifying identity rather
than row counts. This restart check passed at 73cd3a8: 1 baseline, 1 stock, 2
nonces and 1 schema row matched after restart. New exact-head CI results must be
verified before claiming startup or full workflow success.

Physical storage/WAL remains unavailable: read-only SQL 8,402,623 logical bytes,
2 baseline rows/1 stock row; can_inspect_wal=false. No privilege changes. Deploy
metadata exposes historical/live status, not retained-artifact fetchability.
Protected external backup and controlled Render restart/collector continuity
remain blockers. 400 MiB peak target requires a representative continuous test
with total-process/container accounting; neither these synthetic results nor the
post-SIGKILL memory drop meet that acceptance criterion. Staging stays HOLD.

Starting head verified against GitHub and local checkout:
1ca1bb21f96e3c56815d175aa7dab3899a61cb32, Draft PR #21.
Staging remains 96f3000588bd11cd069d91a7402d34fb5651b58d,
autoDeploy=no, trigger=off, one Gunicorn worker / two request threads.

Read-only 300-second metrics through 2026-10-22 20:35 Asia/Bangkok show
526,000,130 bytes (501.633 MiB) against 536,870,900 bytes (~512 MiB),
97.975% used and 10.367 MiB headroom. The plateau began at 18:50.
CPU returned to about 0.00037 cores; memory did not return to its prior plateau.
This supports retained allocation/accounting, but cannot distinguish live Python
objects, native allocation, allocator retention or container page cache.

Historical build logs for the exact live deploy identify pandas 2.3.3,
numpy 2.5.4, yfinance 0.2.66, curl_cffi 0.16.3, cryptography 50.0.2,
psycopg 3.2.13 and cp314 wheels. Runtime warning paths also identify Python 3.14.
The full successful-install list is captured as disposable CI constraints in
memory-evidence/render-build-96f3000-constraints.txt. It does not configure Render.
Python version alone has not been established as the cause of excess memory.

Extended offline diagnostic exercises three cycles of 64 cold and 64 warm
history reads, then 256 reads with two concurrent callers. Warm reads must avoid
provider calls; all I/O is synthetic and network/process guards remain active.
It records installed dependency versions and OS/Python thread counts per phase.
The CI matrix compares Windows/Linux Python 3.12/3.14 with observed build
dependency constraints. Artifact names include Python version to avoid collisions.

Fresh Windows Python 3.12.14 result: 177 passed / 22 skipped (PostgreSQL unavailable).
Extended diagnostic peak 107.414 MiB. Three after-clear RSS values:
100.316, 100.547, 100.480 MiB. Cache capped at 118 frames / 8,326,080
accounted bytes; expiry retained one frame / 70,560 bytes. Rotation isolation
and position results unchanged; zero market downloads or added background threads.
Local psycopg is absent and reported as null rather than claimed equivalent.
Single-process synthetic RSS excludes Gunicorn master, real provider allocations,
container page cache and representative live traffic. CI results must be checked
at the new exact head before claiming Linux/3.14 acceptance.

Source inspection finds scanner scan/top-pick/catalyst caches, multi-radar payload
cache and per-symbol trigger quote cache. The scanner scan has its own two-worker
executor, so two Gunicorn threads do not bound total request-internal concurrency.
Server monitor can add a daemon thread when enabled; offline guard disables it.
No live monitor configuration or live object sizes have been established here.
These are hypotheses for future profiling, not grounds to alter Scanner V4.10.

Physical storage/free space and WAL headroom, protected backup, retained rollback
and exact return artifacts, and actual Render restart persistence remain gates.
Historical live/deactivated statuses do not prove artifacts can still run.
No live load, ingest, restore, deploy, restart, merge, Production change, paid
resource, trading order or Scanner engine modification is authorized by this audit.
