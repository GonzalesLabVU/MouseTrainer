$ErrorActionPreference = "Stop"
$repoRoot = "C:\Users\Max\Documents\Classes\Gonzales Lab\Behavioral\mousetrainer"
Set-Location $repoRoot

$env:WEBAPP_STATUS_API_KEY = [System.Environment]::GetEnvironmentVariable("WEBAPP_STATUS_API_KEY", "Machine")
& ".\webapp\.venv\Scripts\python.exe" -m uvicorn app:app --app-dir ".\webapp" --host 127.0.0.1 --port 8000
