"""Kommandozeile: `python -m app.cli {migrate|seed}`.

- `migrate`: Alembic bis `head` (Plattform plus registrierte Challenge-Migrationen).
- `seed`: migrate + idempotenter Seed der neutralen Demo-Konten und der registrierten Schritte
  (nur mit `DEMO_MODE`).
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import sessionmaker

from app.core.clock import Clock, FrozenClock, SystemClock
from app.core.db import create_db_engine
from app.core.errors import ApiError
from app.core.settings import Settings
from app.persistence.migrate import upgrade_to_head
from app.plugins import load_challenge_plugin
from app.registry import Registry
from app.services import seed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("command", choices=("migrate", "seed"))
    args = parser.parse_args(argv)

    settings = Settings()
    registry = Registry()
    load_challenge_plugin(settings, registry)
    engine = create_db_engine(settings.resolved_database_url)
    try:
        upgrade_to_head(engine, registry)
        if args.command == "migrate":
            print("migrate: ok")
            return 0
        clock: Clock = (
            FrozenClock(settings.app_frozen_now) if settings.app_frozen_now else SystemClock()
        )
        with sessionmaker(engine, expire_on_commit=False)() as session:
            try:
                seed.provision(session, settings, registry, clock)
            except ApiError:
                print("seed: refused (DEMO_MODE is off)", file=sys.stderr)
                return 2
        print("seed: ok")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
