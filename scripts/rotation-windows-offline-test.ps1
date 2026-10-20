param([string]$TestRoot,[string]$PythonPath)
$ErrorActionPreference = 'Stop'
foreach ($file in @('rotation-install.ps1','rotation-credentials.ps1','rotation-scheduled.ps1')) {
    $tokens=$null; $errors=$null
    [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors.Count) { throw 'SCRIPT_SYNTAX_FAILED' }
}
New-Item -ItemType Directory -Path (Join-Path $TestRoot 'runtime'),(Join-Path $TestRoot 'secrets') -Force | Out-Null
$key = ConvertTo-SecureString 'synthetic-key-for-offline-test' -AsPlainText -Force
$secret = ConvertTo-SecureString 'synthetic-child-secret' -AsPlainText -Force
$payload = @{protection='DPAPI_CURRENT_USER';owner_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;key_ciphertext=(ConvertFrom-SecureString $key);secret_ciphertext=(ConvertFrom-SecureString $secret)}
$credentialPath = Join-Path $TestRoot 'secrets\credentials.dpapi.json'
[IO.File]::WriteAllText($credentialPath,($payload | ConvertTo-Json))
if ([IO.File]::ReadAllText($credentialPath).Contains('synthetic-child-secret')) { throw 'PLAINTEXT_PERSISTED' }
$check = ConvertTo-SecureString $payload.secret_ciphertext
if ($check.Length -ne $secret.Length) { throw 'DPAPI_ROUNDTRIP_FAILED' }
$check.Dispose(); $key.Dispose(); $secret.Dispose()
[IO.File]::WriteAllText((Join-Path $TestRoot 'config.json'),(@{task_name='Rotation Offline Test Nonexistent';python_path=$PythonPath} | ConvertTo-Json))
$mock = @'
import json, os, pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1])
ok = os.environ.get('ALPACA_DATA_KEY_ID') == 'synthetic-key-for-offline-test' and os.environ.get('ALPACA_DATA_SECRET_KEY') == 'synthetic-child-secret'
(root / 'mock-result.json').write_text(json.dumps({'environment_ok': ok}))
print('synthetic-child-secret')
print('synthetic-child-secret', file=sys.stderr)
sys.exit(0 if ok else 3)
'@
[IO.File]::WriteAllText((Join-Path $TestRoot 'runtime\capital_rotation_automation.py'),$mock)
# Run twice to exercise atomic replacement of scheduler.json on Windows PS 5.1.
foreach ($attempt in @(1,2)) {
    $captured = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'rotation-scheduled.ps1') -InstallRoot $TestRoot 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'WRAPPER_TEST_FAILED' }
    if (($captured | Out-String).Contains('synthetic-child-secret')) { throw 'CHILD_OUTPUT_LEAK' }
}
$result = Get-Content (Join-Path $TestRoot 'mock-result.json') -Raw | ConvertFrom-Json
if (-not $result.environment_ok) { throw 'PROCESS_ENV_FAILED' }
'WINDOWS_OFFLINE_OK'
