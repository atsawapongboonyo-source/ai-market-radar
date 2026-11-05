# Explosive Momentum Scanner — research module V1

**Status:** offline prototype, not deployed, not scheduled, not live, no orders.

## Objective
Flag anomalous early price/volume behavior around **+10% to +30%** before
potential further attention. This does **not** predict a 400% move or guarantee
detection before Top Gainers lists. Avoid look-ahead and survivorship bias.

## Implemented pure-function prototype
`explosive_momentum_research.detect(symbol, bars)` uses 21 completed
chronological regular-session daily bars: latest close-to-previous-close return
10–30%; latest volume / median of prior 20 bars >=3; latest
close*volume >=$1m; price >=$1. Missing/invalid bars fail closed.
Returns FLAGGED_FOR_REVIEW, NO_FLAG or BLOCKED and explainable reasons.
No provider calls, keys, persistence, routes, threads or Scanner changes.

**Important limitation:** daily bars detect at/after daily close. This prototype
cannot detect a move *during* premarket or intraday, nor claim it precedes
Top Gainers. The intraday version requires properly licensed timestamped
extended-hours trades/quotes, market-wide universe coverage, event-time replay
and latency/freshness checks.

## Next-stage design (not implemented)
1. Define coverage: exchange-listed US equities, min market cap/float and
   price bands; handle splits, halts, offerings and corporate actions.
2. Read-only streaming or frequent polling with explicit provider/feed metadata,
   timestamp, regular/premarket/after-hours session and stale-data blocking.
3. Detect 1/5/15-minute gain acceleration, relative volume vs **same clock-time**
   historical baseline, turnover, spread, bid/ask liquidity, trade count and
   halt/reopen patterns. Do not treat IEX as consolidated SIP volume.
4. Tier alerts: WATCH (early acceleration), REVIEW (10–30% + liquidity),
   OVEREXTENDED (chasing risk), BLOCKED (stale/missing/halts).
5. Separate catalyst classifier (SEC filings, earnings, news) with source
   attribution, no invented catalyst. Distinguish dilution/reverse-split risks.
6. Backtest historical **point-in-time** full universe including delisted names,
   realistic spread/slippage/halts, alerts per day, precision, false positives,
   time-to-leaderboard and forward returns. Paper observation before live alerts.
7. Add read-only mobile view and optional Telegram only after evidence gates,
   resource budget, consent and staging validation.

## Isolation and release
Feature branch separate from Stock Radar V2 PR #21 and Rotation Staging.
Do not merge main, deploy Production or Staging, change paid resources, create
tasks, call trading APIs or send orders without separate approval.
