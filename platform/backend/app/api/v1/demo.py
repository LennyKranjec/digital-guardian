"""`/demo/accounts`: nur mit `DEMO_MODE` (sonst 404); Konten kommen aus Plattform und Registry."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import RegistryDep, SettingsDep
from app.core.errors import ApiError
from app.services import seed

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoAccountOut(BaseModel):
    username: str
    password: str
    role: str
    label: str


@router.get("/accounts")
def accounts(settings: SettingsDep, registry: RegistryDep) -> list[DemoAccountOut]:
    if not settings.demo_mode:
        raise ApiError(404, "not_found", "Not found")
    return [
        DemoAccountOut(username=a.username, password=a.password, role=a.role, label=a.label)
        for a in seed.all_demo_accounts(registry)
    ]
