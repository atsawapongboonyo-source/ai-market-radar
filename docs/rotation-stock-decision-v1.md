# Capital Rotation — Stock Drilldown & Entry Decision V1

Status: design / implementation pending. Branch based on Phase 3 commit 0401c2e. No production deployment.

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
