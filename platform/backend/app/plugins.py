"""Lädt das optionale Challenge-Paket `<challenge_dir>/backend/plugin.py` (Funktion `register`)."""

import importlib.util
from pathlib import Path

from app.core.settings import Settings
from app.registry import Registry


def load_challenge_plugin(settings: Settings, registry: Registry) -> bool:
    """`True`, wenn ein Plugin gefunden wurde; ohne Plugin bleibt die Plattform leer."""
    path = Path(settings.challenge_dir) / "backend" / "plugin.py"
    if not path.is_file():
        return False
    spec = importlib.util.spec_from_file_location("challenge_plugin", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load challenge plugin: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register(registry)
    return True
