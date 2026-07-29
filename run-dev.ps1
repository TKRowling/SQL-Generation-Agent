$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $BackendPython)) {
    throw "Virtual environment not found. Create .venv in the project root and install backend\requirements-dev.txt."
}

if (-not (Test-Path (Join-Path $Root "backend\.env"))) {
    throw "backend\.env is missing. Copy backend\.env.example to backend\.env and configure it."
}

if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    throw "frontend\node_modules is missing. Run npm install inside frontend first."
}

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Root\backend'; & '$BackendPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$Root\frontend'; npm run dev"
)

Write-Host "Backend and frontend terminals started. Open http://localhost:5173"
