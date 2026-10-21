# Capital Rotation Phase 3 — PostgreSQL staging

Scope: Draft PR #15 only. No main merge, production configuration, production
deploy, trading orders, new resources, disk expansion or autoscaling.

## Storage design

`ROTATION_DATABASE_URL` is the **existing staging database internal URL**, stored
only as a Render environment secret on `srv-dbbo8gs9v7es73fskc0g`. Presence of this
variable selects PostgreSQL. An empty/invalid value or failed migration fails
startup; connection failures never fall back to SQLite. Do not put its value in
commands, screenshots, logs, issues or source control. The PostgreSQL driver is
restricted to Rotation's optional requirements; scanner source is unchanged.

An additive startup migration creates schema `rotation`, `publications`, `nonces`
and `schema_version`. Session primary key prevents duplicate session records;
nonce composite primary key and an expiry index enforce bounded replay tracking.
NOT NULL, shape/length and timestamp constraints are present. A transaction-level
advisory lock serializes **all** writers (including empty-store writes, pruning
and capacity checks) across threads/processes/instances. Database errors roll
back publication and nonce together and return a fixed 503; no driver exception
or DSN is logged. Connections close per request (existing staging uses 1 worker,
2 threads); statement/lock/connect timeouts bound resource use. Publication
retention remains 32 sessions and nonce retention 601 seconds/4096 entries.

### Safe first cutover

The previous free-service SQLite file is ephemeral and cannot be assumed
accessible to a replacement instance. We do not delete that file or the Windows
collector's daily evidence/outbox. Before deploy, record the current public JSON
and its digest and verify the existing local public outbox agrees. The new
PostgreSQL schema starts empty, then the **existing** collector republishes the
latest validated public summary. This is not a transfer of all historical
SQLite rows. Collector private evidence stays on Windows.

To prevent an unexpired pre-cutover request from being accepted by the new
empty nonce table, the first migration persists `signature_not_before` using
PostgreSQL time +301 seconds. This covers the protocol's +300 second permitted
future skew. Requests timestamped before this floor return 503 CUTOVER_GUARD.
The floor is inserted once and is never reset on restart/redeploy. After about
5 minutes, the existing collector can publish with a new signature. Never set
the floor to zero on staging; only disposable tests do that. Old signatures
remain rejected even during cutover. Normal replay rejection is HTTP 409 and
expired signatures are 401.

## Verification before any production activation

1. Confirm exact service/database IDs, workspace, same region, current branch and
   deployed commit; database autoscaling must remain false and disk 1 GB.
2. Set the existing Internal URL as ROTATION_DATABASE_URL using Render's secret
   UI or an authenticated in-memory API workflow. Keep all existing env vars.
3. Deploy only Rotation Staging after Windows/Linux and PostgreSQL 18 CI pass.
   Startup performs the additive migration under an advisory lock.
4. Wait for the cutover floor, run the existing Scheduled Task, then independently
   verify 14 symbols x21 IEX daily bars, Decimal return calculations, ranking,
   regime, freshness, signature/partial/stale/rollback HTTP results. Upload only
   the allowlisted public projection; never credentials, account data or bars.
5. Capture one accepted signed request **locally**. Replay must be 409; duplicate
   body/new nonce 200 UNCHANGED; wrong key 401; partial/stale 422. Concurrent tests
   must produce one accepted nonce with no duplicate session records.
6. Record public digest and nonce/publication counts, replace the staging
   instance, then read the dashboard **before** allowing collector republication.
   Digest/counts must persist. Replay the identical signed request within its
   300-second validity window; require 409. A replay performed after expiry
   cannot prove nonce persistence (it would get 401 even without a database).
7. `rotation_backup.restore_drill(PublicStore(...))` snapshots source tables in a
   repeatable-read transaction, serializes/deserializes bytes, restores to
   temporary tables with constraints/indexes, compares every row in both
   directions, and rolls back. Source data are unchanged. This is a logical
   restore drill, **not** proof of Render PITR or durable off-instance backups.
8. Check SQL relation/database sizes, Render service/DB RAM and storage trend;
   do not expand resources. Repeat scanner isolation probe and main-site HTTP
   smoke checks; confirm production revision/config unchanged.

## Current verification limits

Deployment and runtime results must be recorded from actual observations. A
passing disposable PostgreSQL CI job does not prove that the existing Render
service has migrated or that Windows → Render → PostgreSQL works. A successful
collector upload while storage is EPHEMERAL does not prove persistence. Do not
claim Phase 3 complete until live restart/replay and backup drill are verified.
Production approval remains a separate step; PR stays Draft.
