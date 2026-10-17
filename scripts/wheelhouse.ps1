<#
.SYNOPSIS
  Legt ein Python-Wheelhouse AUSSERHALB des Repos an (Standard: ~/.rakathon/wheelhouse), damit
  scripts/setup.ps1 -Offline ohne Netz installieren kann. Einmal mit Netz ausfuehren.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$wheelhouse = if ($env:RK_WHEELHOUSE) { $env:RK_WHEELHOUSE } else { Join-Path $HOME '.rakathon/wheelhouse' }
New-Item -ItemType Directory -Force $wheelhouse | Out-Null
$py = Join-Path $root 'platform/backend/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Error 'platform/backend/.venv fehlt: zuerst scripts/setup.ps1 ausfuehren.'; exit 2 }
# Build-Abhaengigkeiten exakt wie in [build-system] requires gepinnt (z. B. setuptools==82.0.1): ohne sie
# scheitert `pip install -e` offline, weil pip dafuer eine isolierte Build-Umgebung anlegt.
$buildRequires = & $py -c "import sys, tomllib; print('\n'.join(tomllib.load(open(sys.argv[1], 'rb'))['build-system']['requires']))" "$root/platform/backend/pyproject.toml"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $py -m pip download --disable-pip-version-check --quiet --dest $wheelhouse "$root/platform/backend[dev]" @($buildRequires)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "wheelhouse: OK ($wheelhouse)"
