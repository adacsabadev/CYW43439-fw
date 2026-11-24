param(
    [string]$SdkPath = 'E:\VSCODE_COPILOT_Root_New\rpi-pico2\.tools\pico-sdk',
    [string]$PicotoolPath = 'E:\VSCODE_COPILOT_Root_New\rpi-pico2\.tools\picotool',
    [string]$PioasmPath = 'E:\VSCODE_COPILOT_Root_New\rpi-pico2\.tools\pico-sdk-tools\pioasm'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot 'build\stock-0065'

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
