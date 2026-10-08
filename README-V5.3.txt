AI Market Radar V5.3 — Server Auto Monitor

Scope
- Adds a Render-side background monitor over the existing V5.2 alert-only workflow.
- Existing Scanner, Top Pick ranking, Premarket Gate, Opening Confirmation, Final Decision, Position Engine and Multi-Radar formulas are unchanged.
- No brokerage connection and no order placement are added.

Candidate selection
- Uses the existing Top Pick Engine.
- Monitors up to 3 non-SKIP, non-CACHED candidates by default.
- Negative high-impact catalyst candidates are excluded fail-closed.
- Candidate list inherits the existing Top Pick cache, so ranking is not recalculated every 30 seconds.

Auto data
- Yahoo 1-minute pre/post-market data.
- Previous regular-session close.
- Premarket last price and Premarket %.
- Current price.
- Regular-session Open.
- Stable first-15-minute Opening High / Low.
- Relative Volume remains optional and is not guessed.

Session safety
- America/New_York timezone.
- Weekend: no monitoring.
- Before 09:30 ET: Premarket only, no entry.
- 09:30–09:45 ET: collect Opening Range, no entry.
- 09:45–16:00 ET: RTH Monitor.
- After 16:00 ET: no new entry monitoring.
- Missing current-day data or quotes older than 180 seconds fail closed.
- Market holidays naturally fail closed because current-day Yahoo data is missing/stale.

Signal flow
- Price below Buy Low: WATCH.
- First observation at/above Buy Low inside allowed zone: TRIGGER TOUCHED.
- Second consecutive observation: existing Opening Confirmation is re-run.
- Opening must return ENTRY1.
- Existing Final Decision is then re-run.
- Final Decision must return CONFIRMED.
- Only then Telegram sends AI RADAR — ENTRY SIGNAL.
- A ticker is alerted at most once per server process/session date.

Render environment
- SERVER_AUTO_MONITOR_ENABLED=1
- SERVER_AUTO_MONITOR_POLL_SECONDS=30
- SERVER_AUTO_MONITOR_MAX_CANDIDATES=3
- TELEGRAM_BOT_TOKEN=<secret>
- TELEGRAM_CHAT_ID=<chat id>

Status
- GET /api/server-monitor-status
- Scanner UI shows Server, Session, Last Check, candidate state and price.

Important
- Alert only; user still reviews the Scanner/Webull before placing any order.
- Free Yahoo data can lag Webull.
- V5.3 intentionally starts with Yahoo to validate end-to-end server monitoring. A later data-feed adapter can replace Yahoo without changing decision logic.
