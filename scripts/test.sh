#!/usr/bin/env bash
# Alle Qualitaetspruefungen, Abbruch beim ersten Fehler. E2E=1 aktiviert zusaetzlich den Playwright-Smoke.
set -euo pipefail
cd "$(dirname "$0")/.."
BACKEND=platform/backend
if [ -x "$BACKEND/.venv/bin/python" ]; then PY="$PWD/$BACKEND/.venv/bin/python"
elif [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then PY="$PWD/$BACKEND/.venv/Scripts/python.exe"
else echo "platform/backend/.venv fehlt: zuerst scripts/setup.sh ausfuehren." >&2; exit 2; fi

step() { echo "==> $1"; }
# Challenge-Backend (challenge/backend) gehoert in jede Schranke, sobald es existiert.
CH=(); if [ -d challenge/backend ]; then CH=(../../challenge/backend); fi
step "ruff check";          (cd "$BACKEND" && "$PY" -m ruff check . ../../tests ../../scripts "${CH[@]+"${CH[@]}"}")
step "ruff format --check"; (cd "$BACKEND" && "$PY" -m ruff format --check . ../../tests ../../scripts "${CH[@]+"${CH[@]}"}")
step "mypy";                (cd "$BACKEND" && "$PY" -m mypy app ../../tests/backend "${CH[@]+"${CH[@]}"}")
step "pytest";              (cd "$BACKEND" && "$PY" -m pytest -q)
step "eslint";              npx eslint .
step "prettier --check";    npx prettier --check .
step "tsc (frontend)";      npx tsc -p platform/frontend --noEmit
step "tsc (design-tokens)"; npx tsc -p platform/packages/design-tokens --noEmit
step "tsc (e2e)";           npx tsc -p tests/e2e --noEmit
step "vitest run";          npm test
step "vite build";          npm run build
if [ "${E2E:-0}" = "1" ]; then step "playwright (E2E-Smoke)"; npm run e2e; fi
echo "test: OK"
