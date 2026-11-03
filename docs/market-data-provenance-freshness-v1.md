# Market-data provenance and freshness contract (draft, non-deployed)

Scope: Stock Radar V2 staging research only. This document does not change the existing Production Scanner, publish quotes, or authorize trading.

## Verified source map (Production commit 36cae7b)
| Surface | Data origin | Resolution | Cache | Interpretation |
|---|---|---|---|---|
| Legacy watchlist /api/scan | yfinance through app.py | daily 1d history for analysis | scan result 600 seconds | analytical snapshot, **not live** |
| /api/trigger-quote | trigger_monitor.py yfinance history, prepost=True | 1m bars | 10 seconds | most recent bar, **not tick-by-tick** |
| Server Auto Monitor | server_auto_monitor.py yfinance history, prepost=True | 1m bars | depends on calling workflow | stale if observed bar >180 seconds in premarket evaluation |
| Multi Radar | multi_radar.py yfinance | daily 1d | 600 seconds | daily snapshot |
| Rotation / Stock Drilldown (development) | Alpaca IEX | EOD historical bars | persisted publication | EOD, **not consolidated SIP live** |

Do not infer real-time market-wide pricing from frontend refresh frequency or an HTTP cache miss.

## Proposed response contract for a future V2 view
Each displayed price or decision should include: `source`, `feed` (IEX, SIP, Yahoo or UNKNOWN), `data_kind` (EOD_BAR, INTRADAY_1M_BAR, SNAPSHOT or UNKNOWN), `observed_at_utc` (market-data bar time), `fetched_at_utc` (backend retrieval time), `age_seconds` (calculated against observed_at_utc), `session` (PRE, REGULAR, POST, CLOSED, UNKNOWN), `freshness` (FRESH, STALE, UNKNOWN), and `as_of_label`.

Rules: never label Yahoo 1m, IEX EOD, or a cached response as 'Live' without separate feed/latency verification; never substitute server fetch time for market observation time; mark missing timestamps UNKNOWN; do not imply that a stale EOD bar is a broken feed while the market is closed. During open-market intraday decisions, if observation age exceeds the applicable policy threshold (currently 180 seconds in the premarket monitor), display STALE and block fresh-entry claims. Cache status must be displayed independently of source freshness.

## Verification gates before implementation/deploy
1. Offline unit tests for missing, future, naive, and timezone-aware timestamps; cache hit with stale observation; market session boundaries and holidays.
2. Confirm feed rights and actual timestamp semantics for each endpoint; distinguish Alpaca IEX from SIP and historical from streaming.
3. Keep the current Scanner route responses unchanged; introduce metadata only in isolated V2 code with backward-compatible schema.
4. Run CI and staging soak; preserve restart investigation, PostgreSQL/WAL and rollback HOLD gates. No merge, staging deploy, Production change, paid service, or trading orders in this draft.
