<#
.SYNOPSIS
  Ein Befehl: richtet bei Bedarf ein (scripts/setup.ps1), dann Backend (127.0.0.1:8000) und Frontend (127.0.0.1:5173).
.PARAMETER Offline
  Setup ohne Netz (Wheelhouse + npm-Cache), siehe docs/ENVIRONMENT.md.
#>
param([switch]$Offline, [int]$BackendPort = 8000, [int]$FrontendPort = 5173)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root 'platform/backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py) -or -not (Test-Path (Join-Path $root 'node_modules'))) {
  & (Join-Path $PSScriptRoot 'setup.ps1') -SkipBrowser -Offline:$Offline
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Push-Location "$root/platform/backend"; try { & $py -m app.cli seed } finally { Pop-Location }
Start-Process powershell -WorkingDirectory "$root/platform/backend" -ArgumentList '-NoExit', '-Command', "& '$py' -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $BackendPort --reload"
$env:VITE_PORT = "$FrontendPort"; $env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"
Start-Process powershell -WorkingDirectory $root -ArgumentList '-NoExit', '-Command', 'npm run dev -w platform/frontend'
Write-Host "Backend: http://127.0.0.1:$BackendPort/api/v1/health   Frontend: http://127.0.0.1:$FrontendPort   (Konten: admin / user, Passwort siehe docs/ENVIRONMENT.md)"
