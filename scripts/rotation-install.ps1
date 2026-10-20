param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'AIMarketRadarCapitalRotation'),
    [switch]$PromptCredentials,
    [switch]$RegisterTask
)
$ErrorActionPreference = 'Stop'
$taskName = 'AI Market Radar Capital Rotation Local'
$repoRoot = Split-Path $PSScriptRoot -Parent
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Python executable missing' }
$installFull = [IO.Path]::GetFullPath($InstallRoot)
$localFull = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
if (-not $installFull.StartsWith($localFull,[StringComparison]::OrdinalIgnoreCase)) { throw 'Install must stay in user LocalAppData' }
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
# Private inherited ACL: only this Windows SID and LocalSystem have access.
$acl = [IO.Directory]::GetAccessControl($InstallRoot,[Security.AccessControl.AccessControlSections]::Access)
$acl.SetAccessRuleProtection($true,$false)
foreach ($oldRule in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($oldRule) }
foreach ($sid in @($identity.User.Value,'S-1-5-18')) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)), 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
[IO.Directory]::SetAccessControl($InstallRoot,$acl)
foreach ($folder in @('runtime','secrets','daily')) { New-Item -ItemType Directory -Path (Join-Path $InstallRoot $folder) -Force | Out-Null }
Get-ChildItem -LiteralPath $repoRoot -Filter 'capital_rotation_*.py' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $InstallRoot 'runtime') -Force
}
foreach ($script in @('rotation-credentials.ps1','rotation-scheduled.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $script) -Destination (Join-Path $InstallRoot $script) -Force
}
$revision = (& git -C $repoRoot rev-parse HEAD 2>$null)
$manifest = @{}
Get-ChildItem -LiteralPath (Join-Path $InstallRoot 'runtime') -Filter 'capital_rotation_*.py' -File | ForEach-Object {
    $manifest[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
}
$config = @{task_name=$taskName;python_path=$PythonPath;owner_sid=$identity.User.Value;calendar_coverage='2026-2028';check_interval_minutes=15;installed_revision=$revision;runtime_hashes=$manifest}
$configPath = Join-Path $InstallRoot 'config.json'
$temporary = $configPath + '.tmp'
[IO.File]::WriteAllText($temporary,($config | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
if ([IO.File]::Exists($configPath)) { [IO.File]::Replace($temporary,$configPath,[NullString]::Value) }
else { [IO.File]::Move($temporary,$configPath) }
if ($RegisterTask) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $existing -and $existing.Description -notlike 'AI Market Radar isolated local IEX research*') { throw 'Task name belongs to another task' }
    $taskArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot 'rotation-scheduled.ps1') + '" -InstallRoot "' + $InstallRoot + '"'
    $action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $taskArguments -WorkingDirectory $InstallRoot
    $periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($periodic,$logon) -Principal $principal -Settings $settings -Description 'AI Market Radar isolated local IEX research. Calendar gated, user DPAPI, no trading.' -Force | Out-Null
}
if ($PromptCredentials) {
    # Visible dialog is explicitly requested; no credentials in command arguments.
    Start-Process -WindowStyle Normal -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $InstallRoot 'rotation-credentials.ps1') + '"'),'-InstallRoot',('"' + $InstallRoot + '"'))
}
Write-Output (@{install_root=$InstallRoot;task_name=$taskName;task_registered=[bool]$RegisterTask;credential_dialog_opened=[bool]$PromptCredentials} | ConvertTo-Json -Compress)
