param(
    [string]$TargetRoot = "C:\mousetrainer"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force $TargetRoot | Out-Null

Copy-Item (Join-Path $root "start_webapp.ps1") (Join-Path $TargetRoot "start_webapp.ps1") -Force

Write-Host "Synced local webapp wrapper to $TargetRoot"
