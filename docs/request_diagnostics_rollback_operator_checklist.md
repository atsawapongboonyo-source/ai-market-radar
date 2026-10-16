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

## Read-only preflight update — 2026-10-16

- Render connector confirms service `srv-daek7uqd0e5s738riq40` remains `main`, `autoDeploy=yes`, `autoDeployTrigger=commit`, 1 instance, 0.5 CPU / 512 MB.
- Current live deploy is `dep-db3qeoff3r2c7389mu90`, commit `0eca2343ee06d2118fab347cb3c5a70773d49e3e`. This is a **baseline identifier**, not a proven rollback operation.
- GitHub comparison of draft PR branch against `main`: 90 commits ahead, zero behind, 28 changed files. Confirm the exact diff again before any release; a merge would trigger automatic deployment.
- CI #176 (run 38911201519) passed 11/11 isolated jobs, including monitor-enabled Gunicorn with a CI-only stub. This does not reproduce production SIGSEGV 139 or verify rollback.
- Operator-reported Render flags: monitor enabled, Telegram boot test off, request diagnostics absent/default off. No secret values were collected.
- **Rollback access and execution remain unverified.** An operator must confirm the Render dashboard offers an actionable rollback/redeploy control for the baseline or confirm an authorized Git revert path, taking into account automatic deployments. Do not click rollback/redeploy or alter production as part of this verification.
- **HOLD**: No merge, production deploy, env edits or rollback have been authorized.

## Operator dashboard verification — 2026-10-16

- Operator screenshot confirms Render's `Manual Deploy` dropdown exposes `Deploy a specific commit`, alongside `Deploy latest commit`, `Clear build cache & deploy`, and `Restart service`.
- This establishes a **visible potential rollback route**, NOT proof that the historical baseline SHA can be selected, that an old deployment can be restored successfully, or that the operator has executed a rollback.
- Candidate rollback baseline remains `0eca2343ee06d2118fab347cb3c5a70773d49e3e`, observed live on Render. A rollback deploy would be a production change and requires explicit authorization.
- Do not invoke any deployment or restart as part of preflight. A separate operator check of commit selection (without confirmation) may further establish feasibility, but must not submit a deployment.
- **HOLD DEPLOY** pending explicit approval for merge and separate diagnostics flag activation; no production action authorized.

## Operator verified commit picker and Auto-Deploy side effect — 2026-10-16

- Operator screenshot of Render `Deploy a specific commit` dialog confirms baseline `0eca234` is listed and selectable, with an input for a commit SHA. No commit was deployed during this inspection.
- **Critical UI warning:** Render explicitly states `Auto-Deploy will be disabled for this service to prevent accidental deploys.` Therefore a rollback via specific-commit deployment will change the auto-deploy setting. After any separately authorized rollback, confirm the service is running the intended baseline, then explicitly decide when to restore auto-deploy; do not automatically re-enable it while an unsafe `main` tip remains.
- Visibility of the baseline and this warning increases rollback-path confidence but does not prove a successful deploy or operational recovery. Operator should close the dialog without selecting/deploying.
- Release still requires explicit authorization for merging PR #18 (auto-deploy) and separately for enabling `RADAR_REQUEST_DIAGNOSTICS=1`. **HOLD PRODUCTION DEPLOY.**
