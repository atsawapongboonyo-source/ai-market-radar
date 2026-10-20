param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -eq 'Desktop') { $env:PSModulePath = Join-Path $PSHOME 'Modules' }
$config = $null
$keySecure = $null
$secretSecure = $null
$process = $null
$psi = $null
$exitCode = 2
try {
    $config = Get-Content -LiteralPath (Join-Path $InstallRoot 'config.json') -Raw | ConvertFrom-Json
    $nextCheck = $null
    try {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $config.task_name
        $nextCheck = $taskInfo.NextRunTime.ToUniversalTime().ToString('o')
    } catch { }
    $schedulerPath = Join-Path $InstallRoot 'scheduler.json'
    $temporary = $schedulerPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temporary,(@{task_name=$config.task_name;next_check_utc=$nextCheck} | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
    if ([IO.File]::Exists($schedulerPath)) { [IO.File]::Replace($temporary,$schedulerPath,[NullString]::Value) }
    else { [IO.File]::Move($temporary,$schedulerPath) }
    $credentialError = $false
    try {
        $stored = Get-Content -LiteralPath (Join-Path $InstallRoot 'secrets\credentials.dpapi.json') -Raw | ConvertFrom-Json
        if ($stored.protection -ne 'DPAPI_CURRENT_USER' -or
            $stored.owner_sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'Wrong account' }
        $keySecure = ConvertTo-SecureString $stored.key_ciphertext
        $secretSecure = ConvertTo-SecureString $stored.secret_ciphertext
        if ($keySecure.Length -eq 0 -or $secretSecure.Length -eq 0) { throw 'Empty' }
    } catch { $credentialError = $true }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $config.python_path
    $runnerPath = Join-Path $InstallRoot 'runtime\capital_rotation_automation.py'
    $psi.Arguments = '"' + $runnerPath + '" --root "' + $InstallRoot + '"'
    if ($credentialError) { $psi.Arguments += ' --error CREDENTIALS_UNAVAILABLE' }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.WorkingDirectory = Join-Path $InstallRoot 'runtime'
    $psi.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    if (-not $credentialError) {
        foreach ($entry in @(@('ALPACA_DATA_KEY_ID',$keySecure),@('ALPACA_DATA_SECRET_KEY',$secretSecure))) {
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($entry[1])
            try { $psi.EnvironmentVariables[$entry[0]] = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        }
    }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    # Never forward child stdout/stderr or exceptions to task logs/tool output.
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(480000)) { $process.Kill(); throw 'Timeout' }
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0 -and $exitCode -ne 2) { throw 'Unexpected runner failure' }
    $stdout = $null; $stderr = $null
} catch {
    # A fixed safe marker only. Existing successful data are never removed.
    $failurePath = Join-Path $InstallRoot 'wrapper-error.json'
    $temporary = $failurePath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary,(@{error_code='WRAPPER_FAILED';updated_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json))
        if ([IO.File]::Exists($failurePath)) { [IO.File]::Replace($temporary,$failurePath,[NullString]::Value) }
        else { [IO.File]::Move($temporary,$failurePath) }
    } catch { }
    # Last-resort atomic fail-closed view even when Python cannot start.
    try {
        $health = @{status='BLOCKED';error_code='WRAPPER_FAILED';last_check_utc=[DateTime]::UtcNow.ToString('o')}
        $healthPath = Join-Path $InstallRoot 'health.json'
        $healthTemp = $healthPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
        [IO.File]::WriteAllText($healthTemp,($health | ConvertTo-Json))
        if ([IO.File]::Exists($healthPath)) { [IO.File]::Replace($healthTemp,$healthPath,[NullString]::Value) }
        else { [IO.File]::Move($healthTemp,$healthPath) }
        $htmlPath = Join-Path $InstallRoot 'rotation-dashboard.html'
        $htmlTemp = $htmlPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
        [IO.File]::WriteAllText($htmlTemp,'<!doctype html><html><meta charset="utf-8"><title>Rotation Health</title><h1>BLOCKED</h1><p>Error Code: WRAPPER_FAILED</p><p>No candidates. Check local automation health.</p></html>')
        if ([IO.File]::Exists($htmlPath)) { [IO.File]::Replace($htmlTemp,$htmlPath,[NullString]::Value) }
        else { [IO.File]::Move($htmlTemp,$htmlPath) }
    } catch { }
    $exitCode = 2
} finally {
    if ($null -ne $psi) {
        $psi.EnvironmentVariables.Remove('ALPACA_DATA_KEY_ID')
        $psi.EnvironmentVariables.Remove('ALPACA_DATA_SECRET_KEY')
    }
    foreach ($secure in @($keySecure,$secretSecure)) { if ($null -ne $secure) { $secure.Dispose() } }
    if ($null -ne $process) { $process.Dispose() }
    $stored = $null; $entry = $null; $psi = $null
}
# Optional publisher executes only AFTER the credential-bearing child is disposed.
# No Alpaca variables are passed; publication failure does not break local collection.
if ($exitCode -eq 0 -and (Test-Path -LiteralPath (Join-Path $InstallRoot 'publisher.json'))) {
    $publisherProcess = $null
    try {
        $publisher = Get-Content -LiteralPath (Join-Path $InstallRoot 'publisher.json') -Raw | ConvertFrom-Json
        if ($publisher.enabled -eq $true) {
            $publishInfo = New-Object Diagnostics.ProcessStartInfo
            $publishInfo.FileName = $publisher.python_path
            $publishInfo.Arguments = '"' + (Join-Path $InstallRoot 'publisher-runtime\rotation_collector_publish.py') + '" --root "' + $InstallRoot + '"'
            $publishInfo.UseShellExecute = $false
            $publishInfo.CreateNoWindow = $true
            $publishInfo.RedirectStandardOutput = $true
            $publishInfo.RedirectStandardError = $true
            $publishInfo.EnvironmentVariables.Remove('ALPACA_DATA_KEY_ID')
            $publishInfo.EnvironmentVariables.Remove('ALPACA_DATA_SECRET_KEY')
            $publisherProcess = New-Object Diagnostics.Process
            $publisherProcess.StartInfo = $publishInfo
            [void]$publisherProcess.Start()
            $publishOut = $publisherProcess.StandardOutput.ReadToEndAsync()
            $publishErr = $publisherProcess.StandardError.ReadToEndAsync()
            if (-not $publisherProcess.WaitForExit(90000)) { $publisherProcess.Kill(); throw 'Publisher timeout' }
            $publishOut = $null; $publishErr = $null
        }
    } catch {
        # Fixed local status, never exception text. Collector exit status stays intact.
        try {
            $path = Join-Path $InstallRoot 'publication-health.json'
            $temporary = $path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
            [IO.File]::WriteAllText($temporary,'{"status":"BLOCKED","error_code":"PUBLISHER_UNAVAILABLE"}')
            if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary,$path,[NullString]::Value) }
            else { [IO.File]::Move($temporary,$path) }
        } catch { }
    } finally { if ($null -ne $publisherProcess) { $publisherProcess.Dispose() } }
}
exit $exitCode
