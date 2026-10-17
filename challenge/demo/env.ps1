<#
  Demo-Umgebung (wird von reset.ps1 und start.ps1 per Dot-Sourcing geladen).
  Fest: eigene Demo-Datenbank, eingefrorene Ankerzeit, DEMO_MODE. Überschreibbar: WAECHTER_LLM (Standard template).
#>
$env:DATABASE_URL = 'sqlite:///data/demo.db'          # relativ zu platform/backend => platform/backend/data/demo.db
$env:APP_FROZEN_NOW = '2026-10-17T09:00:00+02:00'     # Ankerzeit des Szenarios (Demo und Tests)
$env:DEMO_MODE = 'true'
$env:APP_ENV = 'development'
$env:APP_NAME = 'Digital Guardian'                 # Anzeigename oben links (Mensch-Vorgabe)
if (-not $env:WAECHTER_LLM) { $env:WAECHTER_LLM = 'template' }
