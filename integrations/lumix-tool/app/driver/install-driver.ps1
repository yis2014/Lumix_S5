param([string]$ResultPath)

$ErrorActionPreference = 'Stop'
$result = [ordered]@{ ok = $false; step = 'prepare'; message = ''; pnputilExit = $null; output = '' }
$work = $null
try {
    if (-not $ResultPath) { throw 'ResultPath is required.' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator privileges are required.'
    }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('LumixTool-driver-' + [guid]::NewGuid().ToString('N'))
    $package = Join-Path $work 'package'
    New-Item -ItemType Directory -Path $package -Force | Out-Null
    $inf = Join-Path $package 'lumixtool_winusb.inf'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'lumixtool_winusb.inf') -Destination $inf

    $result.step = 'certificate'
    $subject = 'CN=LumixTool Driver Signing'
    $cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object {
        $_.Subject -eq $subject -and $_.Issuer -eq $subject -and $_.HasPrivateKey -and
        $_.NotAfter -gt (Get-Date).AddDays(30) -and $_.NotBefore -le (Get-Date) -and
        ($_.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3')
    } | Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject `
            -FriendlyName 'LumixTool local driver signing' -CertStoreLocation Cert:\LocalMachine\My `
            -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -KeyExportPolicy NonExportable `
            -NotAfter (Get-Date).AddYears(5)
    }
    $cer = Join-Path $work 'lumixtool-driver.cer'
    Export-Certificate -Cert $cert -FilePath $cer -Force | Out-Null
    foreach ($store in @('Root', 'TrustedPublisher')) {
        if (-not (Test-Path ('Cert:\LocalMachine\' + $store + '\' + $cert.Thumbprint))) {
            Import-Certificate -FilePath $cer -CertStoreLocation ('Cert:\LocalMachine\' + $store) | Out-Null
        }
    }

    $result.step = 'catalog'
    # Generate outside package: the catalog must not hash itself or the certificate.
    $catalog = Join-Path $work 'lumixtool_winusb.cat'
    New-FileCatalog -Path $package -CatalogFilePath $catalog -CatalogVersion 2 | Out-Null
    $result.step = 'sign'
    $signature = Set-AuthenticodeSignature -FilePath $catalog -Certificate $cert -HashAlgorithm SHA256
    if ($signature.Status -ne 'Valid') { throw ('Catalog signature failed: ' + $signature.StatusMessage) }
    Copy-Item -LiteralPath $catalog -Destination $package

    $result.step = 'pnputil'
    $lines = & "$env:SystemRoot\System32\pnputil.exe" /add-driver $inf /install 2>&1
    $result.pnputilExit = $LASTEXITCODE
    $result.output = ($lines | Out-String).Trim()
    $result.ok = $result.pnputilExit -in @(0, 3010, 1641)
    if ($result.ok) {
        $result.step = 'complete'
        $result.message = 'Driver package added. Recheck the connected device; PnP ranking may keep an existing driver. A restart or USB reconnect may be required.'
    } else {
        $result.message = 'Windows rejected the driver package. See pnputil output and SetupAPI.dev.log; use the manual Zadig fallback if necessary.'
    }
} catch {
    $result.message = $_.Exception.Message
} finally {
    if ($work) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
    $json = $result | ConvertTo-Json -Depth 5 -Compress
    try {
        [IO.File]::WriteAllText($ResultPath, $json, (New-Object Text.UTF8Encoding($false)))
    } catch {
        # Last-resort diagnostic if the supplied path is unwritable.
        [Console]::Out.WriteLine($json)
    }
}
