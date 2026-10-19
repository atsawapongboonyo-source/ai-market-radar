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

## Bounded diagnostics activation decision gate — 2026-10-16 (plan only)

**Current evidence:** CI #190 (run 38922649012) succeeded 12/12, including two 512 MiB offline Gunicorn lifecycle runs with diagnostics OFF and ON, no external network and a harmless CI-only monitor loop. This is not a peak-RAM or sustained-load measurement and does not resolve exit 139.

**Preconditions before any production action:**
1. Separate explicit approval to merge PR #18 (merge triggers Render auto-deploy). Keep diagnostics absent/OFF and confirm no execution flags changed.
2. Before merge, record exact live SHA, monitor health state and cycle age, recent worker exit codes/502/5xx and memory/latency baselines; verify rollback picker and operator access. Do not infer health from `running:true` alone.
3. After authorized merge, validate default-OFF behavior, response shapes, monitor freshness, worker stability and read-only endpoints. If abnormal, do not enable diagnostics.
4. Obtain a **second separate explicit approval** before setting `RADAR_REQUEST_DIAGNOSTICS=1`. Treat the environment change as a restart/deploy event. Never turn on broker dispatch.

**Suggested observation window, not an automatic deployment instruction:** Compare 15 minutes of pre-change baseline with at least 30 minutes after each authorized change, subject to normal traffic availability. Sample Render memory and HTTP status/latency metrics at available resolution and inspect logs. Record worker PID and REQUEST_START/END only after explicit flag authorization. Avoid secrets and raw paths.

**Stop/rollback criteria:** Any new code 139, OOM or worker timeout; HTTP 502/5xx newly recurring or sustained above baseline; stale/dead monitor; malformed API JSON or changed read-only response contract; unexpected request data in logs; unexplained sustained memory growth or near-limit pressure. These are conservative qualitative triggers, not statistically validated thresholds. Stop activation, restore flag OFF (if ON) with approval, and if regression persists request an authorized rollback to the newly reverified baseline.

**Rollback caveat:** Render's `Deploy a specific commit` dialog warns that it **disables Auto-Deploy**. After rollback, confirm live SHA and stability, and keep auto-deploy disabled until the `main` tip is reconciled and explicitly approved. A visible commit picker is not proof of a successful rollback.

**Decision: HOLD.** No approval to merge, change env, restart, or deploy has been given. This plan does not authorize any production action.
