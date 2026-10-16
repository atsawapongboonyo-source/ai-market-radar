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
