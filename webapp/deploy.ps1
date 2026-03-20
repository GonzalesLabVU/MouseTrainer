param(
    [string]$HostRoot = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $root
Set-Location $repoRoot

$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\\python.exe"

if (-not (Test-Path $venvPython)) {
    py -3.12 -m venv $venvDir
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $root "requirements.txt")

$configDir = Join-Path $root "config"
$clientsPath = Join-Path $configDir "clients.json"
$uiPath = Join-Path $configDir "ui.json"

if (-not (Test-Path $clientsPath)) {
    Copy-Item (Join-Path $configDir "clients.example.json") $clientsPath
}

if (-not (Test-Path $uiPath)) {
    Copy-Item (Join-Path $configDir "ui.example.json") $uiPath
}

if ($HostRoot) {
    New-Item -ItemType Directory -Force $HostRoot | Out-Null
    Copy-Item -Recurse -Force (Join-Path $root "*") $HostRoot
}

Write-Host "Web app prepared."
Write-Host "Local test command:"
Write-Host "  $venvPython -m uvicorn app:app --app-dir $root --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Vercel production flow:"
Write-Host "  1. cd webapp"
Write-Host "  2. vercel --prod"
Write-Host "  3. In Vercel, add a Redis integration and set WEBAPP_STATUS_API_KEY"
Write-Host "  4. Redeploy after environment variable changes"
Write-Host ""
Write-Host "See webapp\\VERCEL.md for the full setup."
