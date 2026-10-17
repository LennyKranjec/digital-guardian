"""App-Fabrik: Settings, Uhr, Datenbank, Middleware, Registry und optionales Challenge-Paket."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import __version__
from app.api.router import build_api_router
from app.core.clock import Clock, FrozenClock, SystemClock
from app.core.db import create_db_engine
from app.core.errors import install_error_handlers
from app.core.headers import install_response_headers
from app.core.logging import configure_logging, install_access_log
from app.core.security import install_csrf_guard
from app.core.settings import Settings
from app.plugins import load_challenge_plugin
from app.registry import Registry


def create_app(settings: Settings | None = None, registry: Registry | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    registry = registry or Registry()
    load_challenge_plugin(settings, registry)
    clock: Clock = (
        FrozenClock(settings.app_frozen_now) if settings.app_frozen_now else SystemClock()
    )
    engine = create_db_engine(settings.resolved_database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.registry = registry
    app.state.clock = clock
    install_error_handlers(app)
    install_csrf_guard(app)
    install_access_log(app)
    install_response_headers(app)  # zuletzt = äußerste Schicht: gilt auch für CSRF-/Fehlerantworten
    app.include_router(build_api_router(registry))
    return app
