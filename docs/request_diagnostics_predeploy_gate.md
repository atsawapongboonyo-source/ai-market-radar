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
