"""`/health` und `/meta`: nur HTTP, die Logik liegt in `services/system.py`."""

from typing import Any

from fastapi import APIRouter

from app.core.deps import EngineDep, RegistryDep, SettingsDep
from app.services import system

router = APIRouter(tags=["system"])


@router.get("/health")
def health(engine: EngineDep) -> system.HealthStatus:
    return system.get_health(engine)


@router.get("/meta")
def meta(settings: SettingsDep, registry: RegistryDep) -> dict[str, Any]:
    return system.get_meta(settings, registry)
