param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $repoRoot "config\remote_status.json"
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

$raw = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$raw.base_url = $BaseUrl.Trim().TrimEnd("/")

$json = $raw | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ConfigPath, $json + [Environment]::NewLine)

Write-Host "Updated remote status base_url in $ConfigPath"
Write-Host "New value: $($raw.base_url)"
