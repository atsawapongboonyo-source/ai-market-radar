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
