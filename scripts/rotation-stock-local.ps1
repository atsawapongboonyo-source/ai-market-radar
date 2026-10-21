param([string]$CollectorRoot = "$env:LOCALAPPDATA\AIMarketRadarCapitalRotation", [string]$FeatureRoot = "$env:LOCALAPPDATA\AIMarketRadarCapitalRotation\stock-decision-v1", [ValidateSet('collect','publish')][string]$Mode='collect')
$ErrorActionPreference='Stop'
$psi=$null;$process=$null;$secureKey=$null;$secureSecret=$null
try {
    $publisher=Get-Content (Join-Path $CollectorRoot 'publisher.json') -Raw | ConvertFrom-Json
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$publisher.python_path
    $runner=Join-Path $FeatureRoot 'runtime\rotation_stock_collector.py'
    $universe=Join-Path $FeatureRoot 'runtime\data\rotation-stock-universe-v1.json'
    $psi.Arguments='"'+$runner+'" '+$Mode+' --root "'+$FeatureRoot+'" --universe "'+$universe+'" --collector-root "'+$CollectorRoot+'"'
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $psi.WorkingDirectory=Join-Path $FeatureRoot 'runtime'
    $psi.EnvironmentVariables['PYTHONPATH']=(Join-Path $CollectorRoot 'publisher-runtime')+';'+(Join-Path $CollectorRoot 'runtime')
    $psi.EnvironmentVariables.Remove('ALPACA_DATA_KEY_ID')
    $psi.EnvironmentVariables.Remove('ALPACA_DATA_SECRET_KEY')
    if ($Mode -eq 'collect') {
        $stored=Get-Content (Join-Path $CollectorRoot 'secrets\credentials.dpapi.json') -Raw | ConvertFrom-Json
        if ($stored.protection -ne 'DPAPI_CURRENT_USER' -or $stored.owner_sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'Wrong account' }
        $secureKey=ConvertTo-SecureString $stored.key_ciphertext
        $secureSecret=ConvertTo-SecureString $stored.secret_ciphertext
        foreach ($entry in @(@('ALPACA_DATA_KEY_ID',$secureKey),@('ALPACA_DATA_SECRET_KEY',$secureSecret))) {
            $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($entry[1])
            try { $psi.EnvironmentVariables[$entry[0]]=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        }
    }
    $process=New-Object Diagnostics.Process;$process.StartInfo=$psi;[void]$process.Start()
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(240000)) { $process.Kill();throw 'Timeout' }
    if ($process.ExitCode -ne 0) { throw 'Worker blocked' }
    $result=$stdout.Result | ConvertFrom-Json
    # Only an explicit allowlist is forwarded. Never print raw errors or credentials.
    $result | Select-Object status,session,symbols_requested,stock_rows,states,backtest_completed_trades,paper_outcomes,audit_sha256,http,response,public_bytes | ConvertTo-Json -Depth 5 -Compress
} catch { Write-Output '{"status":"BLOCKED","reason":"STOCK_WORKER_UNAVAILABLE"}';exit 2 }
finally {
    if ($null -ne $psi) { $psi.EnvironmentVariables.Remove('ALPACA_DATA_KEY_ID');$psi.EnvironmentVariables.Remove('ALPACA_DATA_SECRET_KEY') }
    foreach ($s in @($secureKey,$secureSecret)) { if ($null -ne $s) { $s.Dispose() } }
    if ($null -ne $process) { $process.Dispose() }
    $stored=$null;$entry=$null;$psi=$null;$stdout=$null;$stderr=$null
}
