param(
    [Parameter(Mandatory=$true)][string]$PublisherPython,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'AIMarketRadarCapitalRotation')
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$full = [IO.Path]::GetFullPath($InstallRoot)
$local = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
if (-not $full.StartsWith($local,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid install root' }
if (-not (Test-Path -LiteralPath (Join-Path $full 'config.json'))) { throw 'Existing collector required' }
if (-not (Test-Path -LiteralPath (Join-Path $full 'secrets\rotation-staging-real-signing.dpapi'))) { throw 'Protected staging signing key required' }
if (-not (Test-Path -LiteralPath $PublisherPython)) { throw 'Publisher Python required' }
$destination = Join-Path $full 'publisher-runtime'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
# Separate dependency snapshot leaves the working collector runtime untouched.
$sources = @(Get-ChildItem -LiteralPath $repoRoot -Filter 'capital_rotation_*.py' -File)
foreach ($name in @('rotation_publisher.py','rotation_public_protocol.py','rotation_collector_publish.py')) {
    $sources += Get-Item -LiteralPath (Join-Path $repoRoot $name)
}
foreach ($source in $sources) { Copy-Item -LiteralPath $source.FullName -Destination $destination -Force }
$wrapper = Join-Path $full 'rotation-scheduled.ps1'
$temporary = $wrapper + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'rotation-scheduled.ps1') -Destination $temporary
$backup = Join-Path $full 'rotation-scheduled.before-publisher.ps1'
if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $wrapper -Destination $backup }
[IO.File]::Replace($temporary,$wrapper,[NullString]::Value)
$config = @{enabled=$true;endpoint='https://ai-market-radar-rotation-staging.onrender.com/api/rotation/ingest';python_path=$PublisherPython}
$path = Join-Path $full 'publisher.json'
$temporary = $path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
[IO.File]::WriteAllText($temporary,($config | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary,$path,[NullString]::Value) }
else { [IO.File]::Move($temporary,$path) }
Write-Output '{"publisher_enabled":true,"destination":"STAGING","collector_runtime_changed":false,"task_definition_changed":false}'
