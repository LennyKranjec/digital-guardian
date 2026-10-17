#!/usr/bin/env bash
# Demo in einem Befehl zurücksetzen: löscht NUR platform/backend/data/demo.db, migriert, seedet, prüft.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
py="$root/platform/backend/.venv/bin/python"
[ -x "$py" ] || py="$root/platform/backend/.venv/Scripts/python.exe"
[ -x "$py" ] || { echo "platform/backend/.venv fehlt: zuerst scripts/setup.sh ausführen." >&2; exit 2; }
# shellcheck source=env.sh
source "$here/env.sh"
cd "$root"
export LOG_LEVEL=WARNING   # nur für den Reset: keine Zugriffsprotokolle der Prüfung
exec "$py" "$here/reset.py"
