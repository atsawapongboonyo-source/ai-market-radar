# Rotation Staging restart/ingest audit — 2026-11-03 (read-only evidence)

Status: **HOLD STAGING V2 DEPLOY**. Production and existing Staging were not modified.

## Observations (UTC, Render app logs)
- Ingest POST 200 responses appeared at 22:06:01, 22:21:43, 22:36:01, 22:51:43, 23:06:01, 23:21:43, 23:36:01, 23:51:43, 00:06:01, 00:21:43, 00:36:01, 01:06:01, 01:21:44, 01:36:01, 01:51:44, 02:06:01 and 02:21:43 (sample; not an exhaustive completeness claim).
- Gunicorn master logged 'Handling signal: term' at 22:21:01, 22:51:01, 23:21:01, 23:51:01, 00:21:01, 00:51:01, 01:21:01, 01:51:01, and 02:21:01.
- New instance IDs followed termination; startup logged ROTATION_STORAGE_VERIFICATION, POSTGRESQL_PERSISTENT and restore_drill VERIFIED with 10 publications. This is logical snapshot verification, **not PITR or disaster recovery**.
- Render Events query for 2026-11-02 00:00 through 2026-11-03 03:00 UTC returned no events. No root cause established. Correlation with 15-minute ingest schedule is not proof that ingest triggers shutdown.
- Render staging memory sample over 2026-11-02 20:00 to 2026-11-03 02:30 UTC peaked at 220024830 bytes (~209.8 MiB). This does not rule out unobserved short peaks or platform-side reasons.
- Render Postgres read-only SQL: pg_database_size=8672959 bytes (~8.27 MiB); tables included 10 publications and 1 stock publication; no replication slots. pg_ls_waldir() permission denied; physical WAL/disk use remains **unknown**.
- Latest existing staging deploy: 96f3000588bd11cd069d91a7402d34fb5651b58d (2026-10-21). Auto-deploy OFF. Research PR #21 branch changes have not been deployed.
- Research PR #21 commit 4068cd3 completed Stock Radar and Rotation Web CI successfully, including the new offline freshness tests.

## Release gates (must be independently evidenced)
1. Identify and document cause of repeated SIGTERM using platform-side diagnostics/support or controlled safe observation. Do not assert OOM without evidence.
2. Demonstrate same-instance sustained soak across at least 2 hours, with sampled RAM and request/error rates, and no unexplained termination; if platform forces rotation, explicitly redefine and verify restart-tolerant service-level soak instead of claiming same-instance stability.
3. Prove ingestion integrity and freshness across instance changes: accepted/rejected signature checks, replay/concurrency, timestamps, latest publication age, persisted history, and no duplicate publications.
4. Measure real allocated disk/WAL (Render disk metrics or authorized SQL/console). Database logical size alone is insufficient.
5. Demonstrate rollback and restore on isolated disposable resources before any production consideration; no credentials or real orders in evidence.
6. Explicit approval before any Staging deploy; no merge to main, no Production changes, no paid resource creation.

## Next diagnostic hypothesis
The near-exact 30-minute TERM pattern could be platform lifecycle or external orchestration; inspect Render service lifecycle and any client-side scheduler timestamps in a separate read-only audit. No evidence currently establishes the cause.
