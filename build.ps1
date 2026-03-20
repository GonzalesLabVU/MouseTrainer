param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if ($Clean) {
    Remove-Item -Recurse -Force build, dist, dist_build -ErrorAction SilentlyContinue
}

$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\\python.exe"

function Test-Command($Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-External($FilePath, $Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
}

function Reset-Directory($Path) {
    Remove-Item -Recurse -Force $Path -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $Path | Out-Null
}

function Sync-Directory($SourceDir, $DestDir) {
    New-Item -ItemType Directory -Force $DestDir | Out-Null
    Get-ChildItem -Force $DestDir | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $SourceDir) {
        Copy-Item -Recurse -Force (Join-Path $SourceDir "*") $DestDir
    }
}

function Write-Utf8NoBom($Path, $Value) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value + [Environment]::NewLine, $utf8NoBom)
}

if (-not (Test-Path $venvPython)) {
    if (-not (Test-Command "py")) {
        throw "Python launcher 'py' was not found. Install Python 3.12, then rerun .\\build.ps1 -Clean"
    }

    try {
        & py -3.12 -m venv $venvDir
    } catch {
        throw "Python 3.12 is required. Install it, then rerun .\\build.ps1 -Clean"
    }
}

$version = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($version.Trim() -ne "3.12") {
    throw ".venv is using Python $version. Delete .venv and rerun after installing Python 3.12."
}

$env:PYTHONPATH = Join-Path $root "src"

$requirementsFile = Join-Path $root "requirements.txt"
$iconFile = Join-Path $root "mouse.png"
$iconOutputDir = Join-Path $root "build\\icon"
$iconOutputFile = Join-Path $iconOutputDir "mouse.ico"
Invoke-External $venvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-External $venvPython @("-m", "pip", "install", "-r", $requirementsFile)
Invoke-External $venvPython @("-m", "pip", "install", "pyinstaller")

if (Test-Path $iconFile) {
    Invoke-External $venvPython @("-m", "pip", "install", "pillow")
    New-Item -ItemType Directory -Force $iconOutputDir | Out-Null
    Invoke-External $venvPython @(".\\tools\\make_icon.py", $iconFile, $iconOutputFile)
}

$appVersion = (& $venvPython -c "from mousetrainer.version import DEFAULT_APP_VERSION; print(DEFAULT_APP_VERSION)").Trim()
if (-not $appVersion) {
    throw "Could not resolve application version from src\\mousetrainer\\version.py"
}

$tempDistDir = Join-Path $root "dist_build"
$pyInstallerWork = Join-Path $root "build\\pyinstaller"
$launcherDistDir = Join-Path $tempDistDir "launcher"
$clientDistDir = Join-Path $tempDistDir "client"
Reset-Directory $tempDistDir
Reset-Directory $pyInstallerWork
Reset-Directory $launcherDistDir
Reset-Directory $clientDistDir

Invoke-External $venvPython @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--distpath", $launcherDistDir,
    "--workpath", (Join-Path $pyInstallerWork "launcher"),
    "mousetrainer.spec"
)
Invoke-External $venvPython @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--distpath", $clientDistDir,
    "--workpath", (Join-Path $pyInstallerWork "client"),
    "mousetrainer_client.spec"
)

$launcherExe = Join-Path $launcherDistDir "MouseTrainer.exe"
$clientBundleDir = Join-Path $clientDistDir "MouseTrainerClient"
$clientExe = Join-Path $clientBundleDir "MouseTrainerClient.exe"
if (-not (Test-Path $launcherExe)) {
    throw "Launcher build output not found: $launcherExe"
}
if (-not (Test-Path $clientExe)) {
    throw "Client bundle build output not found: $clientExe"
}

$distDir = Join-Path $root "dist"
$shipDir = Join-Path $distDir "USE_THIS"
$shipConfigDir = Join-Path $shipDir "config"
$shipAppDir = Join-Path $shipDir "app"
$shipVersionsDir = Join-Path $shipAppDir "versions"
$shipReleaseDir = Join-Path $shipVersionsDir $appVersion
$exportDir = Join-Path $root "export"
$exportConfigDir = Join-Path $exportDir "config"
$exportAppDir = Join-Path $exportDir "app"
$exportVersionsDir = Join-Path $exportAppDir "versions"
$exportReleaseDir = Join-Path $exportVersionsDir $appVersion
$exportPackagesDir = Join-Path $exportDir "packages"
$bundleFolderName = "MouseTrainerClient-$appVersion"
$bundleZipName = "$bundleFolderName-win64.zip"
$bundleZipPath = Join-Path $exportPackagesDir $bundleZipName
$packageStageRoot = Join-Path $root "build\\package"
$packageStageDir = Join-Path $packageStageRoot $bundleFolderName

Reset-Directory $distDir
Reset-Directory $shipDir
Reset-Directory $exportDir
Reset-Directory $exportPackagesDir
Reset-Directory $packageStageRoot

Copy-Item -Force $launcherExe (Join-Path $distDir "MouseTrainer.exe")
Copy-Item -Force $launcherExe (Join-Path $shipDir "MouseTrainer.exe")
Copy-Item -Force $launcherExe (Join-Path $exportDir "MouseTrainer.exe")
Copy-Item -Recurse -Force $clientBundleDir (Join-Path $distDir "MouseTrainerClient")
Sync-Directory (Join-Path $root "config") $shipConfigDir
Sync-Directory (Join-Path $root "config") $exportConfigDir
Sync-Directory $clientBundleDir $shipReleaseDir
Sync-Directory $clientBundleDir $exportReleaseDir
Sync-Directory $clientBundleDir $packageStageDir

Compress-Archive -Path (Join-Path $packageStageRoot "*") -DestinationPath $bundleZipPath -Force
$bundleSha256 = (Get-FileHash -Algorithm SHA256 $bundleZipPath).Hash.ToLowerInvariant()
$releaseMetadata = @{
    version = $appVersion
    launch_exe = "MouseTrainerClient.exe"
    package_sha256 = $bundleSha256
    installed_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json
Write-Utf8NoBom (Join-Path $shipReleaseDir ".release.json") $releaseMetadata
Write-Utf8NoBom (Join-Path $exportReleaseDir ".release.json") $releaseMetadata

$activeState = @{
    version = $appVersion
    directory = $appVersion
    launch_exe = "MouseTrainerClient.exe"
    package_sha256 = $bundleSha256
    activated_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json
Write-Utf8NoBom (Join-Path $shipAppDir "active.json") $activeState
Write-Utf8NoBom (Join-Path $exportAppDir "active.json") $activeState

Write-Host ""
Write-Host "Build complete."
Write-Host "Updated:"
Write-Host "  dist\\MouseTrainer.exe"
Write-Host "  dist\\MouseTrainerClient\\"
Write-Host "  dist\\USE_THIS\\MouseTrainer.exe"
Write-Host "  dist\\USE_THIS\\app\\active.json"
Write-Host "  dist\\USE_THIS\\app\\versions\\$appVersion\\"
Write-Host "  dist\\USE_THIS\\config\\"
Write-Host "  export\\MouseTrainer.exe"
Write-Host "  export\\app\\active.json"
Write-Host "  export\\app\\versions\\$appVersion\\"
Write-Host "  export\\config\\"
Write-Host "  export\\packages\\$bundleZipName"
