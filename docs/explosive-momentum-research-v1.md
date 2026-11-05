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

## Intraday V1 offline implementation (2026-11-05)

`explosive_momentum_intraday.detect_intraday` now evaluates 16 contiguous
completed one-minute UTC bars, 15-minute turnover, 5- and 15-minute price
momentum, session-open gain, bid/ask spread and a 10+ prior-session
**same-clock 15-minute volume** baseline. It blocks stale/future bars, gaps,
invalid quotes and incomplete baselines. IEX-only input cannot produce a
full-market REVIEW confirmation: it remains WATCH with PARTIAL_MARKET_FEED.
Outputs REVIEW, WATCH, OVEREXTENDED or BLOCKED, without placing orders.

**Unimplemented production requirements:** point-in-time universe discovery;
market-wide intraday data licensing, SIP quote/trade coverage and provider
integration; corporate-action and halt flags; session-calendar/DST validation;
timestamped news/catalyst attribution; event-time backtest and performance
metrics; live dashboard/Telegram delivery; collector scheduling; staging
load/restart/persistence checks. No claims of pre-leaderboard detection.

The offline detector relies on its caller to provide matching session/feed
and previously completed bars and baseline observations; these provenance
contracts require end-to-end validation before enabling any alert.

## Offline replay harness

`explosive_momentum_replay.replay_snapshots` evaluates supplied
point-in-time snapshots and reports REVIEW/WATCH/OVEREXTENDED/BLOCKED counts
and first REVIEW timestamps per symbol. It does not invent outcomes or
precision statistics. The caller must supply **all** screened symbols,
including non-winners, plus independent future outcomes and contemporaneous
leaderboard timestamps before detection lead time, recall, precision,
false-positive rate or P&L can be measured. No historical full-universe
dataset or live market-wide data is bundled.

## Outcome-evaluation safety gate

`explosive_momentum_evaluation.evaluate_replay` now refuses precision and
recall calculations unless the caller supplies the full screened universe,
a record for each symbol including non-winners, one independently sourced
boolean outcome per symbol and evaluation timestamps after observation.
Incomplete labels, missing screened names and look-ahead fail closed.
When complete, it calculates TP/FP/FN/TN, precision, recall and false
positive rate. This is a **measurement harness**, not a completed historical
study: no real full-market labeled dataset has been evaluated yet.

## Alpaca market-data adapter (read-only)

`explosive_momentum_alpaca.fetch_intraday` supports bounded GET requests
to Alpaca 1-minute bars and latest quotes for an explicit ticker, with no
redirects, account access, order access or scheduled publishing. The adapter
returns feed provenance; IEX is partial-market data. A latest quote is **not**
a historical as-of quote and must never be attached to an older replay event.
No credentials are persisted by this adapter.

**Not yet a verified live connection:** credential access/entitlements, actual
provider response, timestamp matching, 10+ prior-session same-clock baselines
and market-wide coverage still require a local opt-in validation. In particular,
do not call the intraday detector on historical bars using the latest quote:
the live quote may be from the future relative to those bars.
