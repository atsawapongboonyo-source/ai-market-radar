param(
    [ValidateSet('iex','sip')][string]$Feed = 'iex',
    [string]$PythonPath = 'python',
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
function Read-LocalCredential([string]$label) {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Alpaca local read-only test'
    $form.ClientSize = New-Object System.Drawing.Size(560,150)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $caption = New-Object System.Windows.Forms.Label
    $caption.Text = "Paste $label here (Ctrl+V). Stored in this process only."
    $caption.SetBounds(15,15,530,30)
    $box = New-Object System.Windows.Forms.TextBox
    $box.UseSystemPasswordChar = $true
    $box.SetBounds(15,50,530,25)
    $button = New-Object System.Windows.Forms.Button
    $button.Text = 'Continue'
    $button.SetBounds(435,100,110,30)
    $button.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $button
    $form.Controls.AddRange(@($caption,$box,$button))
    $form.Add_Shown({ $box.Focus() })
    try {
        if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'Cancelled' }
        return (ConvertTo-SecureString -String $box.Text -AsPlainText -Force)
    } finally {
        $box.Clear()
        $form.Dispose()
    }
}

$pythonPath = $PythonPath
$repoPath = Split-Path $PSScriptRoot -Parent
$outputRoot = (Resolve-Path -LiteralPath $OutputDirectory).Path
$htmlPath = Join-Path $outputRoot "rotation-$Feed.html"
$auditPath = Join-Path $outputRoot "rotation-$Feed-audit.json"
# Inputs are hidden, never command arguments or persisted environment settings.
try {
    foreach ($name in @('ALPACA_DATA_KEY_ID','ALPACA_DATA_SECRET_KEY')) {
        $secureValue = Read-LocalCredential $name
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        try {
            [Environment]::SetEnvironmentVariable($name, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer), 'Process')
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            $secureValue.Dispose()
            Remove-Variable secureValue,pointer
        }
    }
    $reportArgs = @((Join-Path $repoPath 'capital_rotation_alpaca_report.py'), '--feed', $Feed, '--html', $htmlPath, '--audit-json', $auditPath)
    if ($Feed -eq 'iex') { $reportArgs += '--verify-sip' }
    & $pythonPath @reportArgs
    Write-Host "Local report: $htmlPath"
} finally {
    Remove-Item Env:ALPACA_DATA_KEY_ID,Env:ALPACA_DATA_SECRET_KEY -ErrorAction SilentlyContinue
}
