# Render request diagnostics: release and rollback checklist

Status: DRAFT / NO PRODUCTION AUTHORIZATION. This checklist is documentation, not a deploy command.

## Verified baseline (2026-10-16)
- Render service: `srv-daek7uqd0e5s738riq40`; branch `main`, auto-deploy on commits.
- Production live deploy: `dep-db3qeoff3r2c7389mu90`, commit `0eca2343ee06d2118fab347cb3c5a70773d49e3e`.
- Start command: `gunicorn scanner:app`; one instance, 0.5 CPU / 512 MiB RAM.
- Diagnostics opt-in flag: `RADAR_REQUEST_DIAGNOSTICS=1`; otherwise off.
- Draft PR #18 test workflow run 38861642469 passed (21 unit/integration tests).
- **Do not merge into main** without explicit authorization: Render auto-deploys on main commits.

## Pre-deploy gates
1. Obtain explicit user approval for a production merge/deploy, and separately for enabling request diagnostics.
2. Review complete PR diff, especially `scanner.py` and request middleware; confirm scanner V4.10 scoring and trading flags untouched.
3. Check all required CI on latest commit and check for conflicts with main.
4. Verify Render production deployment SHA, health, crash/restart trends, and current environment flag.
5. Confirm an authorized operator can change the Render env flag and roll back to the verified production commit.
6. Keep real-order dispatch disabled; do not add broker credentials to logs.

## Suggested staged rollout (only after authorization)
1. Merge diagnostics-only code while flag remains absent/off; **this itself triggers auto-deploy**. Observe boot, health, errors, and API response parity.
2. If stable, explicitly approve `RADAR_REQUEST_DIAGNOSTICS=1`. A Render env change may trigger restart/redeploy; watch health.
3. Observe for a short bounded window; correlate REQUEST_START/END, pid, worker exits, HTTP 5xx and memory. A missing END is only evidence of interrupted handling, not proof of crash cause.
4. Never send secrets, request bodies, query strings, or concrete sensitive paths to logs. Limit log retention and access.

## Stop conditions
- New worker crashes/restarts, elevated 5xx or timeout rates, slower API responses, memory pressure, unexpected log content, missing scanner outputs, or monitor regressions.
- Immediately stop rollout and disable `RADAR_REQUEST_DIAGNOSTICS` first when diagnostics enabled; if symptoms persist, roll back application deploy.

## Rollback
1. Set `RADAR_REQUEST_DIAGNOSTICS=0` (or remove it), confirm new Render revision healthy.
2. If code regression persists, restore previously verified production commit `0eca2343ee06d2118fab347cb3c5a70773d49e3e` using Render rollback/redeploy controls, subject to verifying it is still the correct baseline at rollout time.
3. Verify HTTP 200 for health/read-only endpoints, expected scanner behavior, no unintended trade execution, worker health, and logs.
4. Record timestamps, deployed SHA, symptoms and actions in Issue #16. Do not call a rollback successful without checking production state.

## Known limits
- The middleware is not a native crash handler. SIGSEGV/code 139 cannot be caught reliably from Python.
- The diagnostics are process-local and do not resolve Yahoo Finance timeout or worker crashes.
- CI runs on a small Flask app, not the entire production application; CI passing does not guarantee safe production operation.
