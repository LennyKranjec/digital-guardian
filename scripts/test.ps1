<#
.SYNOPSIS
  Alle Qualitaetspruefungen. Bricht beim ersten Fehler mit dem Exitcode des Schritts ab.
.PARAMETER E2e
  Fuehrt zusaetzlich den Playwright-Smoke aus (Ports ueber E2E_BACKEND_PORT/E2E_FRONTEND_PORT, Standard 8100/5273).
#>
param([switch]$E2e)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root 'platform/backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Error 'platform/backend/.venv fehlt: zuerst scripts/setup.ps1 ausfuehren.'; exit 2 }

function Invoke-Step([string]$Name, [string]$Dir, [scriptblock]$Block) {
  Write-Host "==> $Name"
  Push-Location $Dir
  # Windows PowerShell 5.1 macht aus stderr-Ausgaben nativer Programme (z. B. Server-Logs im E2E)
  # sonst Fehler; massgeblich ist allein der Exitcode des Schritts.
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $Block } finally { $ErrorActionPreference = $previous; Pop-Location }
  if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER in '$Name' (Exitcode $LASTEXITCODE)"; exit $LASTEXITCODE }
}

# Challenge-Backend (challenge/backend) gehoert in jede Schranke, sobald es existiert.
$challengeBackend = @(); if (Test-Path "$root/challenge/backend") { $challengeBackend = @('../../challenge/backend') }
Invoke-Step 'ruff check' "$root/platform/backend" { & $py -m ruff check . ../../tests ../../scripts @challengeBackend }
Invoke-Step 'ruff format --check' "$root/platform/backend" { & $py -m ruff format --check . ../../tests ../../scripts @challengeBackend }
Invoke-Step 'mypy' "$root/platform/backend" { & $py -m mypy app ../../tests/backend @challengeBackend }
Invoke-Step 'pytest' "$root/platform/backend" { & $py -m pytest -q }
Invoke-Step 'eslint' $root { npx eslint . }
Invoke-Step 'prettier --check' $root { npx prettier --check . }
Invoke-Step 'tsc --noEmit (frontend)' $root { npx tsc -p platform/frontend --noEmit }
Invoke-Step 'tsc --noEmit (design-tokens)' $root { npx tsc -p platform/packages/design-tokens --noEmit }
Invoke-Step 'tsc --noEmit (e2e)' $root { npx tsc -p tests/e2e --noEmit }
Invoke-Step 'vitest run' $root { npm test }
Invoke-Step 'vite build' $root { npm run build }
if ($E2e) { Invoke-Step 'playwright (E2E)' $root { npm run e2e } }

Write-Host 'test: OK'
exit 0
