# Capital Rotation Alpaca data adapter — isolated pilot

This is a **read-only local research tool**, not the live Render dashboard.
It never calls Alpaca trading endpoints, Webull, or broker order APIs.

## Requirements
- Python 3.12 and IANA timezone data. Linux normally supplies the timezone
  database; Windows Python may need the `tzdata` package. Missing timezone data
  produces `TIMEZONE_DATA_UNAVAILABLE` rather than guessing the UTC offset.
- Alpaca market-data entitlement for the requested ETF symbols. Paper Trading
  keys may authenticate market-data requests, but do **not** guarantee SIP or
  full IEX symbol coverage. Do not purchase a plan before verifying access.
- The pinned NYSE calendar covers scheduled core sessions in 2026-2028,
  reviewed 2026-10-20 against https://www.nyse.com/trade/hours-calendars.
  It handles holidays, early closes, daylight saving time and a 20-minute
  readiness buffer. It cannot detect unscheduled exchange closures.

## Windows PowerShell local pilot

Set keys in the **current PowerShell process only**; do not paste them into
ChatGPT, commit them to Git, put them in screenshots, or include them in logs.
Use the masked desktop dialogs (Ctrl+V works in these text boxes). Older
PowerShell secure console prompts may consume Ctrl+V as a control character.
From the repository folder, with Python 3.12 available as `python`:

```powershell
powershell -NoProfile -STA -ExecutionPolicy Bypass -File scripts/rotation-local.ps1 -OutputDirectory ..
```

The launcher resolves the date automatically, stores HTML and price evidence
outside the repository, then clears both process environment variables.
Use `-PythonPath` for a particular Python executable. Nothing is scheduled.
The CLI also supports `--html` and `--audit-json`; omit the positional date.
An explicit date must equal the latest completed session. Unsupported calendar
years (including a 21-session lookback outside coverage) fail closed.
Closure-gap freshness is derived from that session's scheduled close, not
the daily bar's midnight start timestamp. Raw bar timestamps remain in evidence.

IEX data are **not consolidated US market volume**. If any ETF lacks 21
completed sessions in the feed, output is `BLOCKED` and no candidate list.
The primary adapter makes one bounded request and does not paginate.
The launcher also requests historical SIP once for cross-feed comparison.
If SIP is unavailable, the report labels comparison BLOCKED without claiming
verification; IEX research results can still be displayed. No plan is purchased.
All symbols must have identical last 21 observation dates, so gaps cannot
silently turn a 5-session comparison into different intervals per symbol.
The exact dates must also match the calendar's 21 trailing exchange sessions.

## Calculation and market-data evidence

Each report independently recomputes 5/20-session returns with Decimal
arithmetic from the provider's 21 closing observations per symbol. Tampering,
date gaps, or inconsistent returns block the report. The local audit JSON
contains closes, base dates, base prices and recomputed returns, never secrets.
The optional IEX/SIP comparison records closing-price differences in basis
points and return differences in percentage points. These feeds cover different
markets; equality is not assumed and no arbitrary pass tolerance is imposed.
This is **not an independent vendor check**. A separate licensed source with
matching split adjustment and close conventions still needs to be reconciled
before claiming independently verified market prices.

HTML output is also written on provider failure, replacing any previous
candidate list with BLOCKED. Safe error codes distinguish missing credentials,
authentication failure (401), feed access denial (403), and rate limits (429).
Other provider exceptions are suppressed without printing response content.
Successful IEX access verifies only the requested daily historical data; it
does not establish SIP, streaming, real-time, or redistribution entitlement.

The tool reports *relative price strength*, not actual institutional capital
flows. It cannot produce live intraday momentum, constituent breadth, or
real-time quotes yet.

## Before production
1. Verify entitlement and symbols without sharing credentials.
2. Refresh the pinned exchange calendar when announcements change; address
   unscheduled closures and missing years before unattended operation.
3. Review provider freshness, cache, rate limits, rights for dashboard display,
   memory, and per-worker concurrency; test staging separately.
4. Obtain explicit deployment approval. PR #15 remains draft; **do not merge**
   into main because Render auto-deploys on commit.
