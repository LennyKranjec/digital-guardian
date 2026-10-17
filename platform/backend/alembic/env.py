"""Alembic-Umgebung: URL aus den App-Settings, Metadaten aus Plattform und Registry."""

from sqlalchemy import Engine, MetaData

from alembic import context
from app.core.db import create_db_engine
from app.core.settings import Settings
from app.persistence.models import Base
from app.registry import Registry

_registry = context.config.attributes.get("registry")
target_metadata: list[MetaData] = [
    Base.metadata,
    *(_registry.metadata if isinstance(_registry, Registry) else []),
]


def _engine() -> Engine:
    # Tests und CLI können die Engine vorgeben (config.attributes), sonst gilt DATABASE_URL.
    given = context.config.attributes.get("engine")
    if isinstance(given, Engine):
        return given
    return create_db_engine(Settings().resolved_database_url)


def run_migrations_online() -> None:
    with _engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
