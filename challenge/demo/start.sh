#!/usr/bin/env bash
# Demo starten: Umgebung setzen, mit --reset zuerst zurücksetzen, dann scripts/dev.sh (Backend 8000, Frontend 5173).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# shellcheck source=env.sh
source "$here/env.sh"
if [ "${1:-}" = "--reset" ]; then "$here/reset.sh"; fi
exec bash "$root/scripts/dev.sh"
