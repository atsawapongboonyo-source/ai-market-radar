# Capital Rotation local Windows automation

This opt-in installation is isolated from Flask, Scanner V4.10, production
environment, Render, and trading APIs. Only historical Alpaca IEX stock bars
are requested. SIP verification is deliberately absent from the scheduled job.

## Install

From a trusted checkout of feature/capital-rotation-offline-v1, run Windows
PowerShell 5.1 with Python 3.12 and timezone data available:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/rotation-install.ps1 -PythonPath "C:\absolute\path\python.exe" -PromptCredentials -RegisterTask
```

The only persistent execution-policy bypass is a process command-line option;
the machine/user PowerShell policy is not changed. The masked desktop dialog
accepts both Paper Key ID and Secret. Never pass those values as arguments.

Default installation: `%LOCALAPPDATA%\AIMarketRadarCapitalRotation`. Runtime
modules are copied from this checkout, with SHA-256 hashes and revision in
config.json. The Python executable remains an explicit external dependency;
if it is removed, reinstall with a working Python 3.12 path.

The install directory has inheritance disabled and grants access only to the
installing Windows SID and LocalSystem. The secrets subdirectory inherits this
private ACL. `ConvertFrom-SecureString` without an explicit AES key uses Windows
DPAPI CurrentUser. Both values are encrypted, bound to that Windows account on
that computer. No key contents, plaintext credentials, child stdout/stderr or
provider exception bodies are written to logs or displayed by the scheduled
wrapper. Decrypted values exist transiently in process memory and in the Python
child's environment; they are never Scheduled Task arguments. GUI/secure-string
buffers are disposed and process environment entries are removed on completion.
This protects at-rest storage, not a compromised session of the same user.

## Task and calendar

Task: **AI Market Radar Capital Rotation Local**. It uses the current user's
interactive token, Limited privilege, an indefinite 15-minute trigger, and an
AtLogOn trigger for that user. StartWhenAvailable is enabled; overlapping runs
are ignored, with a second OS file lock in the runner. No Windows password is
stored. A locked but logged-in session can run; a signed-out session cannot.
After a powered-off machine starts, log in to this same Windows account for
catch-up. No real shutdown/reboot is performed by the installer or tests.

Checks can run during market hours but do not download a partial session. The
2026–2028 pinned NYSE calendar handles DST, weekends, scheduled holidays and
13:00 early closes. Data become eligible 20 minutes after core close and are
fetched on the next check (normally 20–35 minutes after close). The buffer is
not a guarantee of provider finality. Emergency closures and announcements
after the calendar review are not automatically discovered. Outside coverage
the job reports BLOCKED; it never guesses holidays or UTC offsets.

## Data, catch-up, and fail-closed behavior

Each daily file must pass all 14 symbols × 21 exact exchange sessions,
independent Decimal recomputation, and classification replay. Valid daily files
are reused without another provider request. Missing sessions since the oldest
valid saved session in the trailing 21-session window are filled chronologically.
Historical backfills explicitly record both collection time and historical
evaluation time. No invented observation dates or synthetic market values are
used. A downtime beyond the supported trailing window reports
CATCH_UP_LIMIT_EXCEEDED for review rather than silently skipping old sessions.

Files in `daily\YYYY-MM-DD.json` have one canonical slot per session. Repeating
a successful task does not create duplicate daily records. The old local
manual research archive is separate; installation starts with a fresh provider
fetch and does not trust imported PASSED labels. Corrupt/tampered daily records
are revalidated and refetched.

Writes use a temporary sibling file, flush/fsync, and atomic rename. History
create-if-absent uses an atomic link. Interrupted writes leave the previous
complete file. Multi-file updates are not a single transaction; the next check
reconciles complete daily files. Disk failure can prevent even an error page
from being updated, so check the Last Run / Check timestamp on a static page.

Dashboard: `rotation-dashboard.html`. Status: `health.json`, `scheduler.json`,
and the fixed-code `wrapper-error.json` if the wrapper itself fails. Error
codes include CREDENTIALS_UNAVAILABLE, AUTHENTICATION_FAILED, FEED_ACCESS_DENIED,
PROVIDER_UNAVAILABLE, CALCULATION_AUDIT_FAILED, MISSING_EXCHANGE_SESSIONS,
CATCH_UP_LIMIT_EXCEEDED, and WRAPPER_FAILED. Error views contain no candidates;
last successful daily evidence is retained separately. HTTP redirects are
refused so authentication cannot be forwarded to another host.

## Verification and maintenance

```powershell
python -m unittest discover -p 'test_capital_rotation*.py'
Get-ScheduledTaskInfo -TaskName 'AI Market Radar Capital Rotation Local'
Start-ScheduledTask -TaskName 'AI Market Radar Capital Rotation Local'
```

The offline suite includes Windows DPAPI round-trip, process-only secret
delivery, suppression of synthetic child secret output, atomic replacement,
deduplication, catch-up, DST/holiday/early-close timing, and fail-closed errors.
CI runs on Windows and Linux; Windows-only DPAPI and locking checks skip on
Linux. Test fixtures never use real credentials or provider network access.

Review credential-status.json and ACL metadata without opening the encrypted
credential file in chat or tools. To change keys, run rotation-credentials.ps1
from the installation with `-InstallRoot`, in a visible `-STA` PowerShell.
To pause, use Disable-ScheduledTask for this exact task name. Reinstallation
updates only this app's runtime/config and task, preserving encrypted keys and
daily evidence. A full production deployment remains a separate decision;
this PR stays draft and must not be merged or deployed by the installer.
