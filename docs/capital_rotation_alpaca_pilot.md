# Capital Rotation Alpaca data adapter — isolated pilot

This is a **read-only local research tool**, not the live Render dashboard.
It never calls Alpaca trading endpoints, Webull, or broker order APIs.

## Requirements
- Python 3.12; no additional Python packages required for the adapter.
- Alpaca market-data entitlement for the requested ETF symbols. Paper Trading
  keys may authenticate market-data requests, but do **not** guarantee SIP or
  full IEX symbol coverage. Do not purchase a plan before verifying access.
- A separately verified last completed US equity exchange session date.
  Do not guess exchange holidays or use the current trading date mid-session.

## Windows PowerShell local pilot

Set keys in the **current PowerShell process only**; do not paste them into
ChatGPT, commit them to Git, put them in screenshots, or include them in logs.
The following prompts do not echo the secret values:

```powershell
$env:ALPACA_DATA_KEY_ID = Read-Host 'Alpaca Paper Key ID'
$secure = Read-Host 'Alpaca Paper Secret' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:ALPACA_DATA_SECRET_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); Remove-Variable secure,ptr }
python capital_rotation_alpaca_report.py 2026-10-16 --feed iex --max-age-hours 96
Remove-Item Env:ALPACA_DATA_KEY_ID,Env:ALPACA_DATA_SECRET_KEY
```

The date shown is an **example**, not a claim about today's last completed
exchange session. Replace it with a verified session date. The age threshold
must reflect actual market closure gaps; do not use a long age threshold to
silently accept genuinely stale data.

IEX data are **not consolidated US market volume**. If any ETF lacks 21
completed sessions in the feed, output is `BLOCKED` and no candidate list.
The adapter deliberately makes one bounded request and does not paginate.

The tool reports *relative price strength*, not actual institutional capital
flows. It cannot produce live intraday momentum, constituent breadth, or
real-time quotes yet.

## Before production
1. Verify entitlement and symbols without sharing credentials.
2. Add authoritative US exchange calendar and scheduled completed-session
   resolution; currently date input is manual.
3. Review provider freshness, cache, rate limits, rights for dashboard display,
   memory, and per-worker concurrency; test staging separately.
4. Obtain explicit deployment approval. PR #15 remains draft; **do not merge**
   into main because Render auto-deploys on commit.
