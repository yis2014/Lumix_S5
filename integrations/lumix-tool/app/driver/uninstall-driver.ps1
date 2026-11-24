param([string]$ResultPath, [switch]$RemoveCertificate)

$ErrorActionPreference = 'Stop'
$result = [ordered]@{ ok = $false; step = 'prepare'; message = ''; pnputilExit = $null; output = '' }
try {
    if (-not $ResultPath) { throw 'ResultPath is required.' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator privileges are required.'
    }
    $pnp = "$env:SystemRoot\System32\pnputil.exe"
    $result.step = 'enumerate'
    $listing = & $pnp /enum-drivers 2>&1
    $result.pnputilExit = $LASTEXITCODE
    $result.output = ($listing | Out-String).Trim()
    if ($result.pnputilExit -ne 0) { throw 'Could not enumerate driver packages; nothing was removed.' }
    # Labels are localized. Match exact field values inside the same blank-line block.
    $packages = @()
    foreach ($block in [regex]::Split($result.output, '(?:\r?\n)[\t ]*(?:\r?\n)')) {
        $published = $null
        $original = $false
        $provider = $false
        foreach ($line in ($block -split '\r?\n')) {
            if ($line -match '[:\uFF1A]\s*(oem\d+\.inf)\s*$') { $published = $Matches[1] }
            if ($line -match '[:\uFF1A]\s*lumixtool_winusb\.inf\s*$') { $original = $true }
            if ($line -cmatch '[:\uFF1A]\s*LumixTool\s*$') { $provider = $true }
        }
        if ($published -and $original -and $provider) { $packages += $published }
    }
    $packages = @($packages | Select-Object -Unique)
    $result.step = 'pnputil'
    foreach ($published in $packages) {
        $lines = & $pnp /delete-driver $published /uninstall /force 2>&1
        $result.pnputilExit = $LASTEXITCODE
        $result.output += "`r`n$published`r`n" + ($lines | Out-String).Trim()
        if ($result.pnputilExit -notin @(0, 3010, 1641)) { throw ('Could not remove ' + $published) }
    }
    if ($RemoveCertificate) {
        $result.step = 'certificate'
        foreach ($store in @('Root', 'TrustedPublisher', 'My')) {
            Get-ChildItem ('Cert:\LocalMachine\' + $store) | Where-Object {
                $_.Subject -eq 'CN=LumixTool Driver Signing' -and $_.Issuer -eq 'CN=LumixTool Driver Signing'
            } | ForEach-Object {
                if ($store -eq 'My') { Remove-Item -LiteralPath $_.PSPath -DeleteKey -Force }
                else { Remove-Item -LiteralPath $_.PSPath -Force }
            }
        }
    }
    $result.ok = $true
    $result.step = 'complete'
    $result.message = 'LumixTool driver packages removed (or already absent). Reconnect USB; normal mode 04DA:2382 uses the Windows MTP driver.'
} catch {
    $result.message = $_.Exception.Message
} finally {
    $json = $result | ConvertTo-Json -Depth 5 -Compress
    try {
        [IO.File]::WriteAllText($ResultPath, $json, (New-Object Text.UTF8Encoding($false)))
    } catch { [Console]::Out.WriteLine($json) }
}
