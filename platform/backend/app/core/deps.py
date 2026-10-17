"""FastAPI-Dependencies: Zugriff auf Settings, Engine, DB-Session und Registry aus dem App-State."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.registry import Registry


def get_session(request: Request) -> Iterator[Session]:
    """Eine Session je Request; Commit/Rollback verantworten die Services."""
    factory = cast("sessionmaker[Session]", request.app.state.session_factory)
    with factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_engine(request: Request) -> Engine:
    return cast(Engine, request.app.state.engine)


def get_registry(request: Request) -> Registry:
    return cast(Registry, request.app.state.registry)


SettingsDep = Annotated[Settings, Depends(get_settings)]
EngineDep = Annotated[Engine, Depends(get_engine)]
SessionDep = Annotated[Session, Depends(get_session)]
RegistryDep = Annotated[Registry, Depends(get_registry)]
