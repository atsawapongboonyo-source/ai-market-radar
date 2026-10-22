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
