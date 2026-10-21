# Capital Rotation — Stock Drilldown & Entry Decision V1

Status: V1 implementation in this branch; live feature deployment and observation gates must be verified separately. Branch based on Phase 3 commit 0401c2e. No production deployment.

## Purpose
Extend the existing Capital Rotation research dashboard with an expandable ETF-to-stock drilldown and an explainable, read-only decision assistant. This is **not** an order execution system or a guarantee of profitability.

## Scope and data contracts
- Keep existing signed Collector → PostgreSQL → Staging flow, nonce replay protection, existing Scanner V4.10, and production service unchanged.
- Map each supported ETF to a versioned, timestamped, source-attributed stock universe. Do not present a sample ticker list as current ETF holdings. Distinguish verified holdings from thematic watchlists (e.g. optical/AI).
- Collect stock OHLCV via approved read-only Alpaca market-data endpoints only; do not call trading endpoints. Use completed sessions only and record feed (IEX), coverage, timestamps and source.
- Compute 5-session and 20-session total price returns and relative returns vs SPY and parent ETF from aligned closes; exclude missing/incomparable histories, corporate-action mismatches, zero-volume or low-liquidity observations. No forward-looking bars.
- Store sanitized derived outputs only; no Alpaca credentials, account data, local audit secrets or raw private files in Staging.
- Use schema migrations and idempotent session keys. Enforce signed payload integrity and freshness, persistent nonce checks and atomic writes.

## Decision engine
States: READY (passes research criteria), WAIT (setup incomplete), AVOID (risk criteria fail), BLOCKED (data missing, stale, inconsistent, unverified or unsupported).
- Rules must be deterministic and explainable, not an opaque arbitrary score.
- Assess sector strength, stock-vs-SPY and stock-vs-sector momentum, trend confirmation, liquidity, volatility, distance from entry trigger, and expected reward/risk after costs.
- Portfolio concentration/correlation warnings require explicitly authorized holdings data. If unavailable show 'portfolio exposure unknown', not 'safe'.
- Show trigger, invalidation/stop reference, timestamp, input evidence, and reason codes. READY means review candidate, never automatic buy.
- Do not force daily signals or a 2–5% daily return target.

## Validation / release gates
1. Unit and integration tests for adjusted returns, aligned sessions, missing bars, holidays/DST, duplicates, stale data, and fail-closed BLOCKED.
2. Walk-forward backtests with no look-ahead/survivorship leakage, fees, spread/slippage, realistic liquidity and benchmark comparisons. Report false positives, drawdown and trade frequency, not only win rate.
3. Paper-trading observation only; compare signals to out-of-sample realized outcomes before considering live usage.
4. Validate 14 ETF baseline remains unchanged; test signed staging ingestion, concurrent requests, restart persistence, RAM and storage limits.
5. Implement mobile-friendly expandable ETF rows and stock tables, clear RESEARCH_ONLY / STAGING labels, evidence date and source.
6. Separate approval required for any main merge, production deploy, production environment changes, added paid resources, or trading actions.

## Implementation order
1. Read existing rotation_staging.py, capital_rotation modules, schemas and tests; write interface tests before modifying behavior.
2. Build stock-universe metadata and historical read-only collector, then validated derived data contract.
3. Add deterministic decision engine and reason codes with tests.
4. Add staging-only stock drilldown UI and endpoint.
5. Run CI, resource checks, end-to-end staging tests and paper observation. Report blockers without claiming completion.

## V1 implementation and operating limits
- Immutable `data/rotation-stock-universe-v1.json` is an issuer-attributed snapshot,
  verified from State Street, iShares and VanEck on 2026-10-21, holdings as of 2026-10-19. Analyze
  only the top 5 by issuer weight for each of all 14 baseline funds. SOXX is from issuer CSV; SMH is a reviewed
  issuer HTML extraction (XLS unavailable), with the exact normalized factual
  extract and hash preserved in data/rotation-stock-smh-source-20261021.txt.
  No thematic list is represented as holdings. Snapshot expiry is 7 calendar days; refresh requires review and a
  new matching client/server universe version. `scripts/rotation_refresh_universe.py`
  reproduces State Street retrieval; its openpyxl dependency is operator-only.
  iShares CSV and VanEck HTML evidence require a separately reviewed refresh;
  do not silently relabel their original known_at time as a new verification.
- `rotation_stock_collector.py collect` fetches 120 completed sessions for the
  deduplicated stock/parent/SPY set with GET market-data IEX split-adjusted daily
  bars. OHLCV and local backtest/paper evidence stay local. Returns are PRICE
  returns, excluding dividends. Missing/duplicate/future/incomparable/zero-volume
  bars fail closed per row. A >50% one-session move is conservatively blocked
  pending corporate-action/outlier review.
- Collection and publication use separate child processes. The opt-in PowerShell
  launcher reuses existing CurrentUser DPAPI credentials without editing the
  installed collector/task. Publish mode rejects a credential-bearing context;
  only the strict signed derived summary is sent. No new scheduled task is
  installed; unattended feature collection is not claimed.
- Immutable rule version eod-v1.1: sector and stock lead SPY/sector in both
  windows, close>SMA20>SMA50 with rising SMA20, median IEX dollar volume >=300k,
  ATR/close <=8%, near prior-20-session-high trigger, relative volume >=1.2 and
  net R:R >=2 after assumed 40 bps per side. SPY-parent candidates require positive
  SPY momentum instead of impossible SPY-relative-to-itself leadership. Stop reference is bounded by prior
  10-session lows and 2 ATR; target must be a previously observed 60-session
  high. No invented 2R target or profitability target. EOD READY is research
  review only, never a live entry instruction or order.
- Portfolio input is optional, local and explicitly authorized. With no current
  authorized snapshot, every row says PORTFOLIO_EXPOSURE_UNKNOWN. Warnings use
  >=10% name weight / >=30% provided parent-sector weight; correlation requires
  >=20 explicitly aligned, dated supplied returns. Portfolio snapshots must have
  an authorized source and timezone-aware timestamp <=24 hours old; otherwise
  exposure stays unknown. This does not estimate unknown ETF look-through.
- Separate `/api/rotation/stocks/ingest` uses a different signature domain and
  the existing persistent global nonce lock/table. New stock_publications has
  idempotent session keys, bounded body/retention and transactions. Stock returns
  must match the existing baseline session's parent/SPY returns; stock writes
  never alter baseline publications. On GET, a corrected/missing baseline
  blocks an incompatible stock view. Existing scanner hooks are unchanged.
- Walk-forward rules never consume future bars for a decision. A membership
  snapshot must have actually been known at the historical decision time.
  Current issuer snapshots cannot establish historical point-in-time membership,
  so current real-data backtest is BLOCKED/0 mature trades, not a return claim.
  Simulator tests cover next-session trigger/gap entry, stop-first ambiguous
  bars, costs, 1% IEX participation limit, <=5-session holding, SPY comparison,
  false positives, trade frequency, closed-trade and daily-mark drawdowns.
  V1 simulator is per-stock; no aggregate portfolio backtest claim.
- First paper signal per session/universe/rule version is persisted locally and does not get
  overwritten by reruns. Only bars whose closes occur AFTER observation may be
  used for 5-session forward outcomes. No order is submitted. Current observation
  has no mature future outcome and cannot demonstrate predictive performance.
- Existing Render staging is linked to feature/capital-rotation-offline-v1.
  Hosted MCP cannot change a service's branch or deploy an arbitrary commit.
  Feature deployment requires changing ONLY that staging service's linked branch
  to feature/rotation-stock-decision-v1 through an authorized Render UI/API path.
  Do not work around this by modifying PR #15, changing production, creating a
  new service or executing remote code via environment variables.

## Observed development evidence (2026-10-21)
- Real local read-only IEX: 73 unique symbols x120 completed sessions, 70
  ETF-stock membership rows. Latest session 2026-10-20. Rules eod-v1.1:
  READY 0, WAIT 39, AVOID 31, BLOCKED 0. No forced signals.
- Independent local Decimal audit verified 420 stock/parent/SPY 5D/20D return
  calculations. All parent/SPY values agree with the live 14-ETF staging summary.
  Existing real DPAPI signing key validates the stock-specific signature locally.
  Strict derived public payload is 54,946 bytes; no raw OHLCV/accounts/credentials
  were transmitted. Feature upload has NOT happened because deployment is gated.
- Browser QA in CI found a 320px overflow, which was corrected by wrapping
  navigation, long research labels and table containers. Both 320/390px native
  details expansion tests passed in the subsequent CI run. Fixtures are clearly
  labelled SIMULATED; they are not evidence of real stock performance.
- Existing Render Staging/Production remain healthy and PR #15 remains at
  0401c2e. Existing PostgreSQL has the baseline publication, with NO stock table
  yet. Feature PostgreSQL migration, concurrency, persistent replay and rollback
  are verified on disposable PostgreSQL 18 CI, NOT yet on Render. Feature RAM,
  restart persistence and end-to-end signed ingest still require feature deploy.
- Paper observations are local, immutable and pending future closes. There are
  zero mature final-rule outcomes. Real-data retrospective backtest remains
  BLOCKED because no historical point-in-time holdings archive was provided.
