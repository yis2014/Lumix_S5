$log = 'F:\work\lumixBin\usbwatch.log'
"watch start $(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8 -Append
$last = '<none>'
while ($true) {
    try {
        $out = pnputil /enum-devices /connected 2>$null
    } catch { $out = @() }
    $ids = @()
    foreach ($line in $out) {
        if ($line -match 'VID_04DA&PID_([0-9A-Fa-f]{4})') {
            $ids += $matches[1].ToUpper()
        }
    }
    $pids = ($ids | Sort-Object -Unique) -join ','
    if ($pids -ne $last) {
        "$(Get-Date -Format 'HH:mm:ss')  PIDs=[$pids]" | Out-File -FilePath $log -Encoding utf8 -Append
        $last = $pids
    }
    Start-Sleep -Seconds 2
}
