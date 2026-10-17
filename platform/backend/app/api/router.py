"""Router-Aufbau: Plattform-Routen plus die von Challenge-Paketen registrierten Router."""

from fastapi import APIRouter

from app.api.v1 import auth, demo, system
from app.registry import Registry


def build_api_router(registry: Registry) -> APIRouter:
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(system.router)
    api_router.include_router(auth.router)
    api_router.include_router(demo.router)
    for router in registry.routers:
        api_router.include_router(router)
    return api_router
