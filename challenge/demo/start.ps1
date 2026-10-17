<#
.SYNOPSIS
  Demo starten: Umgebung setzen, optional zuruecksetzen (-Reset), dann scripts/dev.ps1 (Backend 8000, Frontend 5173).
.DESCRIPTION
  scripts/dev.ps1 startet Backend und Frontend ueber Start-Process; die Umgebungsvariablen dieser Sitzung werden vererbt
  (DATABASE_URL, APP_FROZEN_NOW, DEMO_MODE, WAECHTER_LLM). Eigene Ports: -BackendPort / -FrontendPort.
#>
param([switch]$Reset, [int]$BackendPort = 8000, [int]$FrontendPort = 5173)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $PSScriptRoot 'env.ps1')
if ($Reset) {
  & (Join-Path $PSScriptRoot 'reset.ps1')
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& (Join-Path $root 'scripts/dev.ps1') -BackendPort $BackendPort -FrontendPort $FrontendPort
