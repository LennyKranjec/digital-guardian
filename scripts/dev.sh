#!/usr/bin/env bash
# Ein Befehl: Setup bei Bedarf, dann Backend (127.0.0.1:8000) und Frontend (127.0.0.1:5173). Beenden mit Strg+C.
set -euo pipefail
cd "$(dirname "$0")/.."
if { [ ! -x platform/backend/.venv/bin/python ] && [ ! -x platform/backend/.venv/Scripts/python.exe ]; } || [ ! -d node_modules ]; then
  SKIP_BROWSER=1 bash scripts/setup.sh
fi
if [ -x platform/backend/.venv/bin/python ]; then PY="$PWD/platform/backend/.venv/bin/python"; else PY="$PWD/platform/backend/.venv/Scripts/python.exe"; fi
BACKEND_PORT="${BACKEND_PORT:-8000}"; FRONTEND_PORT="${FRONTEND_PORT:-5173}"
(cd platform/backend && "$PY" -m app.cli seed)
(cd platform/backend && "$PY" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$BACKEND_PORT" --reload) &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT
VITE_PORT="$FRONTEND_PORT" VITE_API_TARGET="http://127.0.0.1:$BACKEND_PORT" npm run dev -w platform/frontend
