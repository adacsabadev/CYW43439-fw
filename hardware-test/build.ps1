param(
    [string]$SdkPath = '',
    [string]$PicotoolPath = '',
    [string]$PioasmPath = '',
    [switch]$Experimental0071
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ProjectRoot
if (-not $SdkPath) { $SdkPath = Join-Path $RepoRoot '.tools\pico-sdk' }
if (-not $PicotoolPath) { $PicotoolPath = Join-Path $RepoRoot '.tools\picotool' }
if (-not $PioasmPath) { $PioasmPath = Join-Path $RepoRoot '.tools\pico-sdk-tools\pioasm' }
$BuildFlavor = 'stock-0065'
$FirmwareDir = ''
if ($Experimental0071) {
    $BuildFlavor = 'experimental-0071'
    $FirmwareDir = Join-Path $RepoRoot 'generated\pico-0071'
    $Converter = Join-Path $RepoRoot 'tools\convert_hcd_to_pico.py'
    & python $Converter `
        --hcd (Join-Path $RepoRoot 'firmware\CYW4343A2_001.003.016.0071.0017.1YN.hcd') `
        --activation-template (Join-Path $RepoRoot 'firmware\cyw43_btfw_43439_0065_pico.h') `
        --output (Join-Path $FirmwareDir 'cyw43_btfw_43439.h')
    if ($LASTEXITCODE -ne 0) { throw 'Experimental firmware conversion failed' }
}
$BuildDir = Join-Path $ProjectRoot ("build\" + $BuildFlavor)

foreach ($required in @(
    (Join-Path $SdkPath 'external\pico_sdk_import.cmake'),
    (Join-Path $PicotoolPath 'picotool\picotool.exe'),
    (Join-Path $PioasmPath 'pioasm.exe')
)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required local tool: $required" }
}

$env:PATH = (Split-Path -Parent $PioasmPath) + ';' + $env:PATH
cmake -S $ProjectRoot -B $BuildDir -G Ninja `
    -DPICO_SDK_PATH="$SdkPath" `
    -DPICOTOOL_FETCH_FROM_GIT_PATH="$PicotoolPath" `
    -Dpioasm_DIR="$PioasmPath" `
    -DPICO_BOARD=pico2_w `
    -DTEST_BT_FIRMWARE_DIR="$FirmwareDir" `
    -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed: $LASTEXITCODE" }

cmake --build $BuildDir
if ($LASTEXITCODE -ne 0) { throw "Build failed: $LASTEXITCODE" }

$Uf2 = Join-Path $BuildDir 'cyw43439_pico_test.uf2'
$Picotool = Join-Path $PicotoolPath 'picotool\picotool.exe'
& $Picotool info -a $Uf2
if ($LASTEXITCODE -ne 0) { throw 'picotool rejected the UF2' }
Get-FileHash -Algorithm SHA256 -LiteralPath $Uf2
Write-Host "UF2 ready: $Uf2"
