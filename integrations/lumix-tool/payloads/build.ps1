# Build all payloads/*.c into Thumb binaries loaded at 0x86370000.
# Usage: pwsh -File payloads/build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$gcc = Join-Path $root 'tools\armgcc\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin\arm-none-eabi-gcc.exe'
$objcopy = Join-Path $root 'tools\armgcc\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin\arm-none-eabi-objcopy.exe'
if (-not (Test-Path $gcc)) { throw "toolchain not found: $gcc" }

# gcc needs a writable temp dir
$env:TMP = Join-Path $root '.tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null

$flags = @('-mcpu=cortex-a7','-mthumb','-O2','-nostdlib','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-Ttext=0x86370000','-Wl,-e,_start')

Get-ChildItem $PSScriptRoot -Filter *.c | ForEach-Object {
    $name = $_.BaseName
    $elf = Join-Path $PSScriptRoot "$name.elf"
    $bin = Join-Path $PSScriptRoot "$name.bin"
    & $gcc @flags -o $elf $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "compile failed: $name" }
    & $objcopy -O binary $elf $bin
    if ($LASTEXITCODE -ne 0) { throw "objcopy failed: $name" }
    $len = (Get-Item $bin).Length
    Write-Host ("{0,-24} {1,6} bytes" -f $name, $len)
    if ($len -gt 0x40000) { throw "$name exceeds the 256 KiB program area" }
}
