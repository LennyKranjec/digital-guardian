# Demo-Umgebung (per `source` laden): eigene Demo-DB, eingefrorene Ankerzeit, DEMO_MODE. WAECHTER_LLM überschreibbar.
export DATABASE_URL='sqlite:///data/demo.db'   # relativ zu platform/backend => platform/backend/data/demo.db
export APP_FROZEN_NOW='2026-10-17T09:00:00+02:00'
export DEMO_MODE='true'
export APP_ENV='development'
export APP_NAME="Digital Guardian"
export WAECHTER_LLM="${WAECHTER_LLM:-template}"
