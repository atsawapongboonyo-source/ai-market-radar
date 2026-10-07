AI Market Radar V5.2 — Trigger Monitor V1

Scope
- Adds an alert-only Trigger Monitor above the existing V5.1 / V4.10 decision flow.
- Existing Scanner, Multi-Radar, Premarket Gate, Opening Confirmation, Final Decision and Position Engine remain unchanged.
- No order placement is added.

Why
- MU on 2026-10-07 showed the main latency bottleneck: the system ranked the correct theme/stock and produced the correct Buy Zone, but the price crossed the Trigger faster than manual re-entry could be completed.
- V5.2 reduces WATCH → Trigger → Recheck latency without changing the underlying thresholds.

Runtime
- Render entrypoint remains gunicorn scanner:app.
- scanner.py now loads scanner_v520.py.
- New read-only API: /api/trigger-quote?ticker=MU
- Quote source: Yahoo 1-minute intraday data with a 10-second server cache.
- Stale quotes older than 5 minutes are never used to confirm a trigger.

Trigger Monitor behavior
- User completes the existing Premarket and Opening checks as before.
- User taps "เริ่มเฝ้า Trigger" once.
- Browser polls approximately every 20 seconds while the page remains open.
- A trigger needs 2 consecutive observations at/above Buy Low.
- If price is more than 0.5% above Buy High, state becomes DONT CHASE.
- On trigger confirmation the monitor automatically re-runs Opening Confirmation with the latest price and updated high/low.
- Only if Opening returns ENTRY1 does it re-run the existing Final Decision.
- ENTRY 1 CONFIRMED is shown only when both existing engines confirm.
- Browser vibration / Notification is used when available.

Safety
- Alert-only and read-only.
- No brokerage credentials.
- No order endpoint.
- Existing decision logic remains authoritative.
- Browser must stay open for monitoring.
- Free intraday data can lag Webull; Webull remains the execution/reference screen.
