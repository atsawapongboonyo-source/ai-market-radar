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
Physical disk/WAL metrics unavailable; rollback artifact 'Build not found'; stock_publications restore drill incomplete; sustained RAM soak and signed ingest/replay through restart incomplete; intermittent Position-to-Rotation double navigation. These remain blockers. This branch is data/docs only and must NOT be deployed or merged to main.
