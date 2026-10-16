# Full runtime smoke test: isolation gate (2026-10-16)

Status: **DESIGN ONLY / HOLD**. This document does not authorize a live import, deploy, merge, or broker operation.

## Verified import risk
- `scanner.py` imports the real legacy scanner and the V5.3.1 extension chain.
- `scanner_v531.py` imports `scanner_v530.py`; V5.3 calls `start_server_monitor()` at import time. The monitor's own enable flag must be verified before a full import.
- Production dependencies include Flask, Gunicorn, pandas and yfinance. An import may transitively initialize market-data clients or background services; do **not** treat an import as automatically side-effect free.

## Required sandbox gates before running
1. Execute only in an isolated CI/job container, never the Render production service. No production environment secrets or tokens.
2. Set `SERVER_AUTO_MONITOR_ENABLED=0`, `RADAR_REQUEST_DIAGNOSTICS=0` initially and every known trading/dispatch switch to its safe disabled value. Audit other import-time effects and outbound calls first.
3. Deny outbound network at the container boundary, not merely by mocking Python HTTP clients. Assert no external service requests or background monitor threads start.
4. Import actual `scanner:app` with no module stubs; assert `RUNTIME_VERSION == "5.3.1"`, the Flask app has expected routes, and the WSGI middleware is absent when diagnostics is off.
5. Repeat in a fresh process with diagnostics enabled; assert middleware wrapping and route-template logging without credentials, bodies, query strings or raw sensitive paths.
6. Exercise only deterministic, read-only endpoints with mocked market data, bounded timeouts and a no-trade sentinel; do not call scan refresh or any endpoint with unknown side effects.
7. Verify clean process shutdown, no unexpected threads, and no native worker crashes; report any skipped checks as **unverified**, never PASS.
8. Reconfirm latest GitHub CI, production SHA, current Render env flag, operator rollback access and separate approvals before considering deployment.

## Current decision
The isolated Flask/Gunicorn tests and offline route contract pass. **Full real-runtime import has not yet been executed**, and safe network isolation plus import-time side-effect review are still required. Remain HOLD DEPLOY.

## Import-chain review update (2026-10-16)

- Confirmed chain: `scanner.py → scanner_v531 → scanner_v530 → scanner_v520 → scanner_v510 → scanner_v494 → legacy_scanner` (additional imports in intermediate modules remain to be audited).
- `scanner_v530.py` invokes `start_server_monitor()` unconditionally at module import; `server_auto_monitor.py` checks `SERVER_AUTO_MONITOR_ENABLED` (default `0`) before starting a daemon thread. Set `SERVER_AUTO_MONITOR_ENABLED=0` explicitly in the isolated test.
- `scanner_v520.py` can start a daemon thread and send a Telegram test message on import when `TELEGRAM_TEST_ON_BOOT=1`. Set `TELEGRAM_TEST_ON_BOOT=0` explicitly and provide no Telegram credentials in the isolated test.
- `scanner_v510.py` registers Multi-Radar endpoints whose handlers call market-data research functions; do not call them in smoke tests without hard provider mocks and network egress denial.
- The previously passing CI #104 only exercised isolated/stubbed modules; the full-runtime import is **not yet proven safe**. No production configuration or runtime changed.
