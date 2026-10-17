"""Einstieg für reset.ps1 / reset.sh (Kern: challenge/backend/waechter/demo.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from waechter.demo import main

if __name__ == "__main__":
    raise SystemExit(main())
