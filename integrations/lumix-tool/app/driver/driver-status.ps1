# Read-only, non-elevated. Fixed JSON keys avoid all localized PnP display labels.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
try {
    $devices = @(Get-PnpDevice -PresentOnly | Where-Object {
        $_.InstanceId -match '^USB\\VID_04DA&PID_(2370|2382)(&|\\)'
    } | ForEach-Object {
        $device = $_
        $values = @{}
        $serviceDetectable = $false
        foreach ($key in @('DEVPKEY_Device_Service', 'DEVPKEY_Device_DriverProvider', 'DEVPKEY_Device_ProblemCode')) {
            try {
                $values[$key] = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName $key -ErrorAction Stop).Data
                if ($key -eq 'DEVPKEY_Device_Service') { $serviceDetectable = $true }
            }
            catch { $values[$key] = $null }
        }
        $guids = $null
        $guidDetectable = $false
        $reg = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\' + $device.InstanceId + '\Device Parameters'
        try {
            # Missing key/value is a detectable absence; access denied remains unknown.
            if (Test-Path -LiteralPath $reg -ErrorAction Stop) {
                $properties = Get-ItemProperty -LiteralPath $reg -ErrorAction Stop
                $guids = @($properties.DeviceInterfaceGUIDs)
            } else { $guids = @() }
            $guidDetectable = $true
        } catch { $guidDetectable = $false }
        [pscustomobject]@{
            instanceId = $device.InstanceId
            service = $values['DEVPKEY_Device_Service']
            serviceDetectable = ($serviceDetectable -or $values['DEVPKEY_Device_ProblemCode'] -eq 28)
            provider = $values['DEVPKEY_Device_DriverProvider']
            problemCode = $values['DEVPKEY_Device_ProblemCode']
            guids = $guids
            guidDetectable = $guidDetectable
        }
    })
    ConvertTo-Json -InputObject $devices -Depth 5 -Compress
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
