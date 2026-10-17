"""Programmatischer Alembic-Zugriff (CLI, Tests, E2E-Start).

Plattform-Migrationen liegen in `alembic/versions`; Challenge-Pakete hängen weitere Ordner über
`Registry.add_metadata(metadata, migrations=...)` ein (Mehrfach-Ordner, ein gemeinsamer Verlauf).
"""

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from app.registry import Registry

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config(engine: Engine, registry: Registry | None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    dirs = [BACKEND_DIR / "alembic" / "versions", *(registry.migration_dirs if registry else [])]
    config.set_main_option("version_locations", os.pathsep.join(str(d) for d in dirs))
    config.attributes["engine"] = engine
    config.attributes["registry"] = registry
    return config


def upgrade_to_head(engine: Engine, registry: Registry | None = None) -> None:
    command.upgrade(_config(engine, registry), "heads")


def downgrade_to_base(engine: Engine, registry: Registry | None = None) -> None:
    command.downgrade(_config(engine, registry), "base")
