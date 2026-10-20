param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$statusPath = Join-Path $InstallRoot 'credential-status.json'
function Write-Atomic([string]$Path, [string]$Text) {
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary,$Text,(New-Object Text.UTF8Encoding($false)))
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary,$Path,[NullString]::Value) }
        else { [IO.File]::Move($temporary,$Path) }
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}
$form = New-Object Windows.Forms.Form
$form.Text = 'AI Market Radar - Save Alpaca credentials with Windows DPAPI'
$form.ClientSize = New-Object Drawing.Size(650,235)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$info = New-Object Windows.Forms.Label
$info.Text = 'Paste the Paper Key ID and Secret. Both stay on this PC, encrypted for this Windows account.'
$info.SetBounds(15,10,620,40)
$keyLabel = New-Object Windows.Forms.Label
$keyLabel.Text = 'Paper Key ID'
$keyLabel.SetBounds(15,60,135,25)
$keyBox = New-Object Windows.Forms.TextBox
$keyBox.UseSystemPasswordChar = $true
$keyBox.SetBounds(155,60,475,25)
$secretLabel = New-Object Windows.Forms.Label
$secretLabel.Text = 'Paper Secret'
$secretLabel.SetBounds(15,100,135,25)
$secretBox = New-Object Windows.Forms.TextBox
$secretBox.UseSystemPasswordChar = $true
$secretBox.SetBounds(155,100,475,25)
$save = New-Object Windows.Forms.Button
$save.Text = 'Encrypt and save'
$save.SetBounds(455,175,175,35)
$save.Add_Click({
    if ([string]::IsNullOrWhiteSpace($keyBox.Text) -or [string]::IsNullOrWhiteSpace($secretBox.Text) -or
        $keyBox.Text -match '\s|[^\x21-\x7E]' -or $secretBox.Text -match '\s|[^\x21-\x7E]') {
        [Windows.Forms.MessageBox]::Show('Paste each complete value without whitespace. Values will not be shown.','Check input') | Out-Null
    } else { $form.DialogResult = [Windows.Forms.DialogResult]::OK; $form.Close() }
})
$form.Controls.AddRange(@($info,$keyLabel,$keyBox,$secretLabel,$secretBox,$save))
$form.AcceptButton = $save
$form.Add_Shown({ $keyBox.Focus() })
try {
    if ($form.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw 'Cancelled' }
    # Avoid binding plaintext user input to a PowerShell cmdlet parameter,
    # which could be captured by module parameter logging on managed machines.
    $keySecure = New-Object Security.SecureString
    foreach ($character in $keyBox.Text.ToCharArray()) { $keySecure.AppendChar($character) }
    $keySecure.MakeReadOnly()
    $secretSecure = New-Object Security.SecureString
    foreach ($character in $secretBox.Text.ToCharArray()) { $secretSecure.AppendChar($character) }
    $secretSecure.MakeReadOnly()
    $character = $null
    $keyBox.Clear(); $secretBox.Clear()
    $payload = [ordered]@{
        version = 1
        protection = 'DPAPI_CURRENT_USER'
        owner_sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        created_utc = [DateTime]::UtcNow.ToString('o')
        key_ciphertext = (ConvertFrom-SecureString $keySecure)
        secret_ciphertext = (ConvertFrom-SecureString $secretSecure)
    }
    # Verify that this account can decrypt without displaying either value.
    $checkKey = ConvertTo-SecureString $payload.key_ciphertext
    $checkSecret = ConvertTo-SecureString $payload.secret_ciphertext
    if ($checkKey.Length -eq 0 -or $checkSecret.Length -eq 0) { throw 'Verification failed' }
    Write-Atomic (Join-Path $InstallRoot 'secrets\credentials.dpapi.json') ($payload | ConvertTo-Json)
    Write-Atomic $statusPath (@{status='STORED';protection='DPAPI_CURRENT_USER';decrypt_verified=$true;updated_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json)
} catch {
    Write-Atomic $statusPath (@{status='NOT_STORED';error_code='CREDENTIAL_ENTRY_NOT_COMPLETED';updated_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json)
} finally {
    $keyBox.Clear(); $secretBox.Clear(); $form.Dispose()
    foreach ($secure in @($keySecure,$secretSecure,$checkKey,$checkSecret)) { if ($null -ne $secure) { $secure.Dispose() } }
    $payload = $null
}
