# Runtime comparison — Staging HOLD

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
