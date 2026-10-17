<#
.SYNOPSIS
  Richtet ein frisches Checkout ein: Python-venv, Backend-Abhaengigkeiten, npm-Pakete, Playwright-Chromium, Demo-Konten.
.PARAMETER SkipBrowser
  Ueberspringt den Playwright-Browser-Download (dann laeuft nur scripts/test.ps1, kein E2E).
.PARAMETER Offline
  Installiert ohne Netz: Python aus dem Wheelhouse (siehe scripts/wheelhouse.ps1), npm aus dem lokalen npm-Cache.
#>
param([switch]$SkipBrowser, [switch]$Offline)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Step([string]$Name, [scriptblock]$Block) {
  Write-Host "==> $Name"
  & $Block
  if ($LASTEXITCODE -ne 0) { throw "Schritt fehlgeschlagen: $Name (Exitcode $LASTEXITCODE)" }
}

$backend = Join-Path $root 'platform/backend'
$venv = Join-Path $backend '.venv'
$venvPython = Join-Path $venv 'Scripts/python.exe'
if (-not (Test-Path $venvPython)) {
  Invoke-Step 'venv anlegen (Python >= 3.12)' {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.14 -m venv $venv; if ($LASTEXITCODE -ne 0) { py -3.12 -m venv $venv } }
    else { python -m venv $venv }
  }
}
$wheelhouse = if ($env:RK_WHEELHOUSE) { $env:RK_WHEELHOUSE } else { Join-Path $HOME '.rakathon/wheelhouse' }
Invoke-Step 'Backend-Abhaengigkeiten' {
  if ($Offline) { & $venvPython -m pip install --disable-pip-version-check --quiet --no-index --find-links $wheelhouse -e "$backend[dev]" }
  else { & $venvPython -m pip install --disable-pip-version-check --quiet -e "$backend[dev]" }
}
Invoke-Step 'Datenbank migrieren + neutrale Demo-Konten seeden (app.cli seed)' {
  Push-Location $backend
  try { & $venvPython -m app.cli seed } finally { Pop-Location }
}
Invoke-Step 'npm ci' { if ($Offline) { npm ci --offline } else { npm ci } }
if (-not $SkipBrowser) { Invoke-Step 'Playwright-Chromium' { npx playwright install chromium } }
Write-Host 'setup: OK'
exit 0
