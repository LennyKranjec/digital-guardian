<#
.SYNOPSIS
  Demo in einem Befehl reproduzierbar zurücksetzen: löscht NUR platform/backend/data/demo.db, migriert, seedet, prüft.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File challenge/demo/reset.ps1
  $env:WAECHTER_LLM = 'cached'; powershell -ExecutionPolicy Bypass -File challenge/demo/reset.ps1   # anderer LLM-Modus
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = Join-Path $root 'platform/backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Error 'platform/backend/.venv fehlt: zuerst scripts/setup.ps1 ausfuehren.'; exit 2 }
. (Join-Path $PSScriptRoot 'env.ps1')
Set-Location $root
$env:LOG_LEVEL = 'WARNING'   # nur für den Reset: keine Zugriffsprotokolle der Prüfung
# Windows PowerShell 5.1 macht aus stderr nativer Programme sonst Fehler; massgeblich ist der Exitcode.
$ErrorActionPreference = 'Continue'
& $py (Join-Path $PSScriptRoot 'reset.py')
exit $LASTEXITCODE
