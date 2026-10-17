#!/usr/bin/env bash
# Richtet ein frisches Checkout ein (Linux/macOS/Git-Bash). OFFLINE=1: Wheelhouse + npm-Cache (docs/ENVIRONMENT.md).
set -euo pipefail
cd "$(dirname "$0")/.."
BACKEND=platform/backend

if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"
elif [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then PY="$BACKEND/.venv/Scripts/python.exe"
else
  python3 -m venv "$BACKEND/.venv" 2>/dev/null || python -m venv "$BACKEND/.venv"
  if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"; else PY="$BACKEND/.venv/Scripts/python.exe"; fi
fi
WHEELHOUSE="${RK_WHEELHOUSE:-$HOME/.rakathon/wheelhouse}"
if [ "${OFFLINE:-0}" = "1" ]; then
  "$PY" -m pip install --disable-pip-version-check --quiet --no-index --find-links "$WHEELHOUSE" -e "$BACKEND[dev]"
else
  "$PY" -m pip install --disable-pip-version-check --quiet -e "$BACKEND[dev]"
fi
(cd "$BACKEND" && "$OLDPWD/$PY" -m app.cli seed)
if [ "${OFFLINE:-0}" = "1" ]; then npm ci --offline; else npm ci; fi
if [ "${SKIP_BROWSER:-0}" != "1" ]; then npx playwright install chromium; fi
echo "setup: OK"
