AI Market Radar V5.3.1 — Premarket Prep + Live Top Pick Rotation

Purpose
- Extend V5.3 without changing the locked Scanner / Top Pick / Opening / Final Decision formulas.
- Prepare candidates automatically before the open.
- Allow Top Pick candidates to rotate during RTH without flapping every few minutes.
- Keep Telegram ENTRY alerts restricted to fully confirmed RTH signals only.

Server schedule (America/New_York)
- Before 08:30 ET: PREMARKET_COLLECT — no heavy re-ranking.
- 08:30–09:20 ET: PREMARKET_PREP — refresh ranking periodically and collect PM price/high/low/gap.
- 09:20–09:30 ET: PREMARKET_LOCK — freeze the active queue into the open.
- 09:30–09:45 ET: OPENING_RANGE — collect first 15-minute range; no entry.
- 09:45–16:00 ET: RTH_MONITOR — live monitor + periodic Top Pick re-ranking.
- After 16:00 ET / weekends: idle.

Premarket data
- Previous regular-session close
- Premarket last
- Premarket %
- Premarket high/low
- Distance to Buy Low
- PM state: DATA_NOT_READY / STALE_DATA / PM_BLOCK / PM_HOT / PM_IN_BUY_ZONE / PM_BELOW_TRIGGER / PM_ABOVE_ZONE
- No Telegram ENTRY alert is sent from Premarket.

Live Top Pick rotation
- Existing active queue: up to SERVER_AUTO_MONITOR_MAX_CANDIDATES (default 3).
- Re-rank interval: SERVER_LIVE_RERANK_SECONDS (default 300 seconds).
- A challenger must beat the weakest active Watch Score by SERVER_LIVE_SWITCH_MARGIN (default 4 points).
- The challenger must maintain the advantage for SERVER_LIVE_SWITCH_CONFIRMATIONS (default 2 re-ranks).
- An active candidate with an in-progress trigger hit is protected from routine replacement.
- Candidates becoming CACHED / SKIP / high-impact-negative / otherwise ineligible are removed immediately.
- New candidate must still pass Trigger -> Opening ENTRY1 -> Final CONFIRMED before Telegram.

Telegram policy
- Premarket preparation is silent.
- Candidate queue changes are silent.
- WATCH / Trigger Touched / ARMED are silent.
- Only ENTRY1 + Final CONFIRMED sends the existing AI RADAR — ENTRY SIGNAL message.

Fail closed
- Missing/stale current-day data: no entry.
- Yahoo quote age > 180 seconds: no entry.
- Missing Premarket % / opening range: no entry.
- Market holiday naturally fails closed when current-day data is absent.
- No auto order / no brokerage action.

UI
- Existing V5.3 Server Auto Monitor card remains.
- V5.3.1 card shows MODE, Active Queue, re-rank policy, Premarket state or live candidate states.

Render environment defaults
- SERVER_AUTO_MONITOR_ENABLED=1
- SERVER_AUTO_MONITOR_POLL_SECONDS=30
- SERVER_AUTO_MONITOR_MAX_CANDIDATES=3
- SERVER_LIVE_RERANK_SECONDS=300
- SERVER_LIVE_SWITCH_MARGIN=4
- SERVER_LIVE_SWITCH_CONFIRMATIONS=2

Notes
- Yahoo 1-minute data is the first end-to-end data feed and can lag Webull.
- Relative Volume remains optional; it is not fabricated.
- Premarket snapshot history is kept in process memory for the current service lifetime. Durable historical storage is a later step.
