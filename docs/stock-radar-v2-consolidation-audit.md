# Stock Radar V2 — Consolidation Audit (research only)

## Baseline
- Parent branch: feature/rotation-stock-decision-v1 at 60d10a3.
- ETF universe: data/rotation-stock-universe-v1.json; 14 funds, 59 unique top-five issuer symbols, verified holdings snapshots. Do not rewrite or expand this as if candidates were ETF constituents.
- Research candidates: data/stock-radar-research-watchlist-v1.json; curated, NOT VERIFIED holdings, NOT EVALUATED, no prices/signals inferred. No collection job is scheduled by this change.
- Rotation Stock Decision: rotation_stock_engine.py, rotation_stock_store.py, rotation_stock_web.py, signed publication. Home projection: rotation_opportunities.py. Navigation: rotation_navigation.py.
- Scanner V4.10 / Production: unchanged and independent. Its signals are not Rotation READY.

## Separation of responsibilities
1. Home: read-only summary of published decisions; never recompute signals or create READY.
2. Scanner: retain current production scanner behavior; never route rotation data into trading endpoints.
3. Rotation: ETF relative-strength research; not measured fund flows.
4. Stock Radar: discover symbols and display a cached, source-labeled decision if and only if a validated signed publication exists. Research candidates without publication display NOT_EVALUATED.
5. Top Pick: presentation/filter of existing scanner picks, not a new scoring engine.
6. Position: existing position view; never infer holdings from a watchlist.

## Safe expansion gates
- Validate symbols, listings, liquidity, corporate actions, data entitlements and timestamp freshness before collection.
- Limit batch size/concurrency; benchmark RAM/CPU and database physical usage against existing 512 MiB service. No extra services or subscription.
- Use the existing signed ingest, publication and PostgreSQL schema when extending eligible universe; do not treat EOD as live or IEX as SIP.
- Keep research candidates separate from verified ETF holdings and never generate READY for missing or stale histories.
- Test scanner isolation, deduplication by ticker and source, navigation 320/390px, signed replay, restart persistence, rollback artifact and sustained soak before any Staging deployment.

## Existing HOLD blockers
Physical disk/WAL metrics unavailable; rollback artifact 'Build not found'; stock_publications restore drill incomplete; sustained RAM soak and signed ingest/replay through restart incomplete; intermittent Position-to-Rotation double navigation. These remain blockers. This branch also contains staging-only read-only research UI, routing and tests. It must NOT be deployed or merged to main while blockers remain.

## Verification checkpoint — 2026-10-22
- PR #21 commit 75e3ab2: research-universe and Rotation Web Isolation CI both passed (Ubuntu, Windows, PostgreSQL).
- Browser navigation probe: widths 320/390/1440, 6 routes each, back/forward, Position close, no overflow, Scanner API blocked.
- CI synthetic 1,500-request probe: no market downloads, no new background threads, RSS +5.559 MiB; not a Render production-like soak.
- Render Staging still serves commit 96f3000, not this PR. Branch remains feature/rotation-stock-decision-v1, auto-deploy off.
- Render observed memory ~433 MiB of 512 MiB on 2026-10-22; do not interpret CI RSS as available headroom for a new deployment.

## Restore and deployment gates (non-destructive)
1. Extend logical restore drill to include rotation.stock_publications in an isolated temp-table comparison, preserving digest/body bytes, session constraints, and transaction rollback. Test empty and populated snapshots with PostgreSQL; do not change live rows or elevate WAL privileges.
2. Validate that the Render rollback target exists and is restorable before deploying; historical 'Build not found' means rollback is NOT verified. Do not attempt a deploy merely to test rollback.
3. Obtain independent physical storage/disk evidence and WAL usage via permitted read-only metrics or operator-approved diagnostics. A SQL row count or serialized snapshot size is not physical disk usage.
4. Perform signed stock ingest replay/concurrency and restart-persistence tests against a disposable isolated database, not live Staging; verify duplicate nonce, old timestamps, conflicting session updates, and baseline binding.
5. Run sustained memory/CPU soak with an explicit stop threshold and measure real Render headroom; no automatic deployment or paid plan changes.
6. Resolve Position-to-Rotation double-tap navigation and rerun the mobile browser probe. Only then reconsider a controlled Staging deployment; Production remains out of scope.

## Signed-ingest CI checkpoint — 2026-10-22
- Commit 4844823: both GitHub workflows succeeded; Rotation Web Isolation jobs Ubuntu, Windows, PostgreSQL succeeded.
- Disposable PostgreSQL job: 22 tests passed; includes empty/populated stock restore drill, concurrent identical nonce replay, restart simulation (new Flask app/store), expired signed timestamp, older conflicting stock publication rejection, baseline mismatch, and failed insert transaction rollback.
- PostgreSQL log lines for intentional constraint/trigger negative tests are expected and do not indicate a failed job.
- These tests do NOT prove a Render instance restart, real external signed collector delivery, physical disk/WAL utilization, rollback artifact availability, or sustained live Staging RAM soak.
- Staging remains deployed at 96f3000; PR #21 is Draft and unmerged. No production deploy or database mutation.

## Production isolation confirmation — 2026-10-22
- Render Production service srv-daek7uqd0e5s738riq40 remains unsuspended on branch main, latest deployment dep-dbccico473hc73aao9e0 at 36cae7b marked live. This is service/deploy status, not an end-to-end freshness guarantee.
- PR #21 remains a Draft on a separate feature branch; neither Production nor Staging was deployed by this checkpoint.
- Existing disposable PostgreSQL probe scripts/rotation_stock_pg_probe.py already exercise a synthetic 70-row publication, 500 read requests, scanner function isolation, no market downloads, no extra threads, bounded RSS delta and pg_total_relation_size for a disposable table. Do not mistake this for Render physical disk/WAL verification or sustained real-instance soak.

## Render RAM gate — 2026-10-22 08:00–10:00 UTC
- Read-only Render Staging memory metric: 465,403,900 bytes (~443.8 MiB) from 08:00–09:40 UTC, rising to 503,111,680 bytes (~479.8 MiB) at 09:50 and 10:00 UTC against a 536,870,900-byte (~512 MiB) limit. Peak headroom ~32.2 MiB (~6.3%).
- These are existing deployed staging instance metrics, not new Stock Radar V2 deployment results. Cause of spike is unverified; do not infer memory leak or deploy safety.
- CI commit d4c3d24: Stock Radar isolation passed, Windows integration and disposable PostgreSQL passed; Ubuntu browser integration still in progress when checked. Prior a2b5df2 Ubuntu failure traced to Position overlay close button intercepting Rotation nav click; navigation and probe updated in d4c3d24.
- Staging deployment remains HOLD pending RAM headroom, physical disk/WAL, rollback artifact and real restart evidence. No live database mutation or production changes.

## Memory / deployment evidence — 2026-10-26
- Render Staging latest live deploy is still `96f3000588bd11cd069d91a7402d34fb5651b58d` from 2026-10-21, not PR #21. Auto-deploy remains off. Do not attribute observed RAM changes to un-deployed V2 code.
- Read-only Render memory samples 2026-10-26 00:00–09:30 UTC (30-minute resolution) returned 20 samples across 16 distinct instance identifiers, minimum ~110.6 MiB, maximum ~159.1 MiB. Separately, higher-resolution 06:00–09:00 UTC samples previously showed peak ~181.9 MiB. The inconsistent sampling/instance turnover means no same-process sustained soak conclusion can be drawn.
- Render service event query 2026-10-22 onward returned no events; this does not establish the cause of instance changes. Do not infer OOM or leak from metrics alone.
- Existing CI on PR #21 head `56ec44a` passed both workflows, including Ubuntu, Windows and disposable PostgreSQL on Python 3.12 and 3.14.8; this is not Render deployment or live resource validation.
- Remain HOLD: prove same-instance steady-state RAM with sustained workload, verify physical disk/WAL and safe rollback, then assess actual restart/persistence. No Production or Render config changes authorized.

## 2026-10-27 00:00–02:30 UTC Render restart investigation (read-only)
- Staging memory samples (5-minute resolution): maximum ~175.7 MiB / 512 MiB, across six distinct instance IDs. This is not evidence of a stable same-instance soak.
- Render application logs show Gunicorn master receiving `Handling signal: term` at 00:21, 00:51, 01:21, 01:51 and 02:21 UTC, followed by orderly `Worker exiting` / `Shutting down: Master` and new Gunicorn startup ~30–40 seconds later. This confirms repeated terminations/restarts, not the underlying platform cause.
- No explicit OOM traceback observed in the inspected app logs; Render events query returned no events. Do not classify as memory leak or OOM, and do not assume a scheduler or Render free-tier behavior without independent evidence.
- Maintain HOLD for V2 staging deploy until a controlled same-instance RAM soak and platform restart reason are available, plus disk/WAL and rollback gates. Existing staging deploy remains 96f3000; Production unchanged.

## 2026-10-27 follow-up: persisted data and sampling caveat
- Read-only Render logs 06:00–10:00 UTC show repeated SIGTERM at 06:06, 06:51, 07:21, 07:51, 08:21, 08:51 UTC, with six `ROTATION_STORAGE_VERIFICATION` messages reporting `POSTGRESQL_PERSISTENT`, `restore_drill.status=VERIFIED`, and five publications each. This supports readable persistent data after process turnover; it does **not** demonstrate PITR, physical WAL capacity or a tested live rollback.
- Memory 06:00–10:00 UTC: sampled maximum ~195.6 MiB of 512 MiB, across seven instance IDs. Subsequent 09:00–13:00 UTC query returned only seven samples (peak ~195.7 MiB) and two app logs, so do not infer the remainder of the requested time window was observed. No evidence of V2 memory improvement until deployed and measured.
- The latest Render live deploy remains `96f3000` from October 21; no V2 deployment authorized. Maintain HOLD until instance turnover reason, sustained same-process soak, disk/WAL, and rollback gates are met.

## 2026-10-27 11:00–13:15 UTC follow-up (read-only)
- Staging app logs show Gunicorn SIGTERM at 11:06, 11:36, 12:06, 12:51 UTC; therefore the earlier ~30-minute cadence is not perfectly uniform (45-minute gap observed). Do not assert a precise restart schedule or platform cause.
- Four `ROTATION_STORAGE_VERIFICATION` startup records each report `restore_drill.status=VERIFIED`. This is a startup logical verification only, not a live database restore, PITR or disk/WAL proof.
- Render RAM: 27 five-minute samples, peak ~189.5 MiB / 512 MiB, five instance IDs; cannot establish same-instance long-duration memory stability. Existing deployed SHA unchanged in last verified deploy check; V2 remains HOLD.
