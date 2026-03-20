param(
    [switch]$SkipFirmwareUpload
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$env:PYTHONPATH = Join-Path $root "src"

if (-not $SkipFirmwareUpload) {
    $firmwareDir = Join-Path $root "firmware\\behavioral_controller"

    if (Get-Command arduino-cli -ErrorAction SilentlyContinue) {
        $boardInfo = arduino-cli board list --format json | ConvertFrom-Json
        $megaPort = $boardInfo.ports |
            Where-Object { $_.matching_boards.fqbn -contains "arduino:avr:mega" } |
            Select-Object -First 1

        if ($megaPort) {
            arduino-cli compile --fqbn "arduino:avr:mega" $firmwareDir
            arduino-cli upload --port $megaPort.address --fqbn "arduino:avr:mega" $firmwareDir
        } else {
            Write-Warning "No arduino:avr:mega board detected; skipping firmware upload."
        }
    } else {
        Write-Warning "arduino-cli is not installed; skipping firmware upload."
    }
}

python -m mousetrainer
