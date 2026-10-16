# Operator rollback checklist — Request Diagnostics (draft, not executed)

**Scope:** Render service `srv-daek7uqd0e5s738riq40`, branch `main`, auto-deploy on commit. This is a planning document, not authorization to merge or change production.

## Before release (operator required)
1. Record currently live Render deploy ID, full Git commit SHA, status, and latest service health. Do not assume an old deployment can be restored merely because it is listed.
2. In the Render dashboard, verify **names and values** of `RADAR_REQUEST_DIAGNOSTICS`, `SERVER_AUTO_MONITOR_ENABLED`, `TELEGRAM_TEST_ON_BOOT`, and any trading/dispatch switches. Do not copy secret values into PRs, logs, screenshots, or chats. The available Render connector cannot read existing environment variables.
3. Verify that an authorized operator can access Render deployment controls and GitHub `main`, and document a rollback path that works with auto-deploy enabled. A revert commit on `main` will itself trigger a new deployment.
4. Prepare rollback criteria: new 5xx/502, worker 139/timeout/OOM, elevated latency, missing request logs, wrong API response, unexpected outbound calls, or unexpected background threads.
5. Obtain explicit, separate approvals for **merge/production auto-deploy** and for **setting `RADAR_REQUEST_DIAGNOSTICS=1`**. Default flag remains OFF; do not enable it as part of a code-only merge without separate approval.

## Release sequence (not yet authorized)
1. Confirm release commit/PR diff and CI results against the exact merge candidate.
2. Merge only in a separately approved release window. Observe Render's automatically triggered deploy; do not manually trigger a duplicate deploy.
3. Check read-only API response and service logs with diagnostics still OFF. Stop if regressions appear.
4. Only after separate flag approval, enable diagnostics, recheck health, and capture bounded sanitized request lifecycle logs. Changing env vars can restart/redeploy the service.
5. If any rollback criterion triggers, stop rollout, restore flag OFF if enabled, and follow the preverified rollback procedure with operator approval. Verify actual live SHA, endpoints and health after rollback.

## Current status
CI #119 passed isolated diagnostics and read-only API smoke. Production environment values, operator rollback access, and rollback execution are **not verified**. **HOLD DEPLOY**.
