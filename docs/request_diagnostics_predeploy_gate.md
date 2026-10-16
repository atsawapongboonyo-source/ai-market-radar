# Request diagnostics pre-deploy gate (2026-10-16)

This is a **review record only**. No merge, Render environment change, or deploy is authorized.

## GitHub verification
- Compare `main...diagnostics/worker-crash-139-20261016`: 29 commits ahead, zero behind; merge base `0eca2343ee06d2118fab347cb3c5a70773d49e3e`.
- 11 changed files: 10 new files, plus `scanner.py` with 13 additions / zero deletions.
- No edits to legacy scanner scoring, candidate ranking, or trade execution modules in this compare.
- Last tested code commit `2f2e8409c4afb1c5d6da2cf6b0a27f73c9fd5058`: GitHub Actions run 38861642469 passed.
- Latest documentation commit must be checked separately if PR is updated again.

## Render verification
- Service `srv-daek7uqd0e5s738riq40`, `main` auto-deploy enabled; one instance, 0.5 CPU / 512 MiB.
- Latest live deploy `dep-db3qeoff3r2c7389mu90` at commit `0eca2343ee06d2118fab347cb3c5a70773d49e3e`.
- Sampled memory in latest observed hour: approximately 225 MB / 537 MB limit. Sampling cannot rule out spikes or native crashes.
- HTTP metrics had zero samples in observed window; do **not** interpret this as proof of application health.

## Remaining gates / explicit HOLD
- Review exact `scanner.py` Flask lifecycle integration against the production runtime, including streaming, exceptions and close callbacks.
- Confirm `RADAR_REQUEST_DIAGNOSTICS` actual Render environment value via authorized environment metadata before deploying; code defaults to off.
- Verify production read-only endpoints and monitor health before and after any authorized rollout.
- Recheck latest GitHub CI and Render live SHA immediately before a deploy.
- Obtain explicit authorization for merging (auto-deploy) and separate authorization to turn the flag on.
- Rollback baseline must be revalidated at the moment of deployment.

**Decision: HOLD PRODUCTION DEPLOY.** The current tests validate an isolated Flask application, not the complete scanner runtime. Continue offline review/tests without changing production.

## Route coverage and lifecycle review (2026-10-16)

- The Render entrypoint `scanner.py` exposes the same Flask app imported from `scanner_v531.py`, which extends `scanner_v530.py`. The opt-in WSGI wrapper therefore covers requests across the extension chain without changing Scanner scoring or entry logic.
- The strict allowlist includes the confirmed legacy routes `/api/scan`, `/api/scan/refresh`, `/api/top-picks`, `/api/catalyst/<ticker>`, `/api/auto-confirm`, `/api/opening-confirm`, and `/api/position-manage`, plus named monitor and radar routes. Other routes remain `UNMAPPED` to avoid disclosing sensitive literal paths.
- `REQUEST_START route=UNMAPPED` is **expected**: Flask has not resolved the URL rule before dispatch. `REQUEST_END` can include an allowlisted route template once Flask resolves it. Correlate by request ID and PID; do not interpret an unmapped START as a missing endpoint.
- A native worker crash can prevent `REQUEST_END`. This is only an in-flight correlation clue, not proof that the request or Yahoo caused the crash.
- The full production app was **not** booted in CI: entrypoint tests stub the legacy and latest scanner imports, while separate tests use minimal Flask/Gunicorn apps. Production deploy remains on hold pending explicit approval and a reversible staged rollout.

## Latest offline release-gate review (2026-10-16)

- CI run #100 (38881411182) passed at commit `136847a9edeccc46caac6c445c487db877361a89`, including AST-derived legacy API route coverage.
- GitHub comparison: branch is 52 commits ahead of `main`, zero behind, 16 changed files. Only `scanner.py` changes the existing production entrypoint (13 added lines); other changes are new diagnostics/tests/docs/workflow.
- Render's latest observed live deployment remains `dep-db3qeoff3r2c7389mu90` at `0eca2343ee06d2118fab347cb3c5a70773d49e3e`. Reconfirm immediately before any rollout.
- Production auto-deploys on `main` commits. **Do not merge this draft PR as an offline test or to enable a preview.**
- Offline route contract covers statically registered legacy API routes, not dynamic registrations in the full extension chain. Full runtime boot, production environment flag value, operational health, and rollback permissions remain unverified.
- **Decision: HOLD DEPLOY.** Next safe action: prepare a staging-equivalent full runtime smoke test with providers/monitor side effects disabled and no broker execution; review results and request separate explicit approvals before merging and before enabling diagnostics.

## Full runtime smoke result (2026-10-16)

- GitHub Actions #115 (run 38890860122) **SUCCESS**: diagnostics and full-runtime-import jobs both passed.
- Full runtime smoke built project dependencies and imported actual `scanner:app` twice in separate Docker containers with `--network none`: diagnostics OFF and ON. `SERVER_AUTO_MONITOR_ENABLED=0`, `TELEGRAM_TEST_ON_BOOT=0`, `LIVE_TRADING=0` were enforced. Route presence, Flask app, runtime version, middleware state, and absence of the named server monitor thread were asserted.
- This verifies **import/startup only**; it does not exercise real scanner API responses, live network integrations, production credentials, or native crash reproduction.
- Latest compare at review: 59 commits ahead, 0 behind `main`; production Render still shows live `0eca2343ee06d2118fab347cb3c5a70773d49e3e`.
- Remaining: inspect Render env flag value with authorized metadata, verify production health/rollback operator access, perform bounded read-only API parity tests, and obtain separate approvals for merge (auto-deploy) and enabling diagnostics.
- **Decision remains HOLD PRODUCTION DEPLOY.**

## Render read-only release review (2026-10-16, after CI #119)

- CI #119 run 38891960049: **SUCCESS** for diagnostics and real-runtime Docker smoke including the read-only `/api/server-monitor-status` API contract with diagnostics OFF and ON. This does not prove all API routes are equivalent.
- Render service `srv-daek7uqd0e5s738riq40` on `main`: `autoDeploy=yes`, `autoDeployTrigger=commit`, one instance, Python runtime, `gunicorn scanner:app`, 0.5 CPU / 512 MB. **Merging into main will trigger deployment.**
- Latest live deploy `dep-db3qeoff3r2c7389mu90` remains commit `0eca2343ee06d2118fab347cb3c5a70773d49e3e`. Prior known deploy `dep-db3fd0l040hc73a04e60` at `4e892fbf594118b97b3c0cf321f23c6afbaaeedd` is deactivated; its existence is not proof that rollback will work.
- No production environment-variable values were read; `RADAR_REQUEST_DIAGNOSTICS`, `SERVER_AUTO_MONITOR_ENABLED`, `TELEGRAM_TEST_ON_BOOT`, and other flags remain **unverified in production**. Do not infer their values from source defaults.
- A rollback runbook must be rehearsed/authorized separately; do not claim rollback is proven. No Render settings, deploys, or production secrets were modified during this review.
- **HOLD** until explicit approval for production merge/auto-deploy and a separate approval to enable diagnostics, plus confirmed rollback access and production flag values.

## CI #127 release-guard verification

- GitHub Actions run 38898592963: **SUCCESS**, all three jobs `release-guard`, `full-runtime-import`, and `diagnostics`.
- Release guard verifies the diagnostics exact opt-in, unchanged locked scanner modules against `origin/main`, and unchanged deployment configuration files. This is a code-diff gate only; it does not inspect production environment variables or prove crash remediation.
- Release approval remains blocked on verifying production flag values and a working operator rollback route. No production deployment or flag changes authorized.

## Additional production crashes (2026-10-16, read-only Render logs)

- 11:12:36 UTC (18:12:36 Bangkok): Gunicorn logged `Worker (pid:20086) was sent code 139!`; a replacement worker PID 20300 booted immediately afterward.
- 12:10:38 UTC (19:10:38 Bangkok): Gunicorn logged `Worker (pid:20300) was sent code 139!`; replacement PID 20436 booted afterward.
- At 11:12:31–34 UTC, access logs include HTTP 200 for `/api/scan`, `/api/top-picks`, and `/api/theme-rotation`. These are temporal observations **not causal proof**. Do not attribute crashes to a particular route or library from proximity alone.
- This evidence was retrieved read-only from the existing production service; no environment variable or deploy changed. Crash diagnostics PR is still unmerged.
- **HOLD** remains; request lifecycle instrumentation would help correlate requests but is not a crash fix. Production flag values and rollback execution are still unverified.

## Focused crash-window review (2026-10-16, read-only)

Read-only Render application log query: 11:08–12:15 UTC, 23 records, no additional pages in this window.

| UTC | Observed event |
| --- | --- |
| 11:12:31–34 | `/api/scan`, `/api/top-picks`, `/api/theme-rotation` each logged HTTP 200 |
| 11:12:36.590 | Worker PID 20086 exited with code 139 |
| 11:12:36.602 | PID 20300 booted |
| 12:10:38.286 | Worker PID 20300 exited with code 139 |
| 12:10:38.298 | PID 20436 booted |
| 12:10:38–43 | Monitor status, scan, rotation, top picks returned HTTP 200 |
| 12:10:45.271 | Worker PID 20436 exited with code 139, ~7 seconds after boot |
| 12:10:45.284 | PID 20652 booted |

**Interpretation limits:** Access logs do not identify the serving worker PID. An HTTP 200 close to a crash is not proof the corresponding endpoint caused it. A rapid post-boot crash is a clue, not proof of an import-time or native-library bug. No request tracing was active. No production changes were made.

**Recommended next offline investigation:** inventory compiled/native dependencies and runtime import behavior; compare memory/worker lifecycle with the log timestamps. Keep separate from opt-in instrumentation rollout; do not modify locked scanner algorithms. **HOLD PRODUCTION DEPLOY.**

## CI #153 completed; release gate remains HOLD

- GitHub Actions run 38905283563: **SUCCESS** across all eight jobs, including the real Gunicorn lifecycle smoke with `RADAR_REQUEST_DIAGNOSTICS=1` in an offline container.
- This confirms only the tested boot/read-only request scenario, not production traffic, memory pressure, market-data calls, or a fix for SIGSEGV 139.
- The readiness estimate for diagnostic instrumentation is ~80% (informal milestone estimate, not measured crash-fix probability). Remaining gates: confirm Render production environment flags without exposing secrets, verify a working rollback operator procedure, obtain separate explicit approvals for merge/auto-deploy and diagnostic flag enablement.
- **HOLD DEPLOY**. No live changes authorized.
