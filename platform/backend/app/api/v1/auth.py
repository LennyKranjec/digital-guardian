"""`/auth/*`: nur HTTP und Cookie-Handling, die Logik liegt in `services/auth.py`."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import PrincipalDep
from app.core.clock import ClockDep
from app.core.deps import RegistryDep, SessionDep, SettingsDep
from app.core.security import SESSION_COOKIE
from app.services import auth
from app.services.auth import Principal

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    subject_id: str | None = None

    @classmethod
    def from_principal(cls, principal: Principal) -> "UserOut":
        return cls(
            id=principal.user_id,
            username=principal.username,
            display_name=principal.display_name,
            role=principal.role,
            subject_id=principal.subject_id,
        )


@router.post("/login")
def login(
    body: LoginRequest,
    response: Response,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> UserOut:
    result = auth.login(
        session,
        clock,
        username=body.username,
        password=body.password,
        ttl_hours=settings.session_ttl_hours,
        lookup=registry.resolve_subject,
    )
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=result.max_age_seconds,
        httponly=True,
        samesite="strict",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return UserOut.from_principal(result.principal)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    principal: PrincipalDep,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> Response:
    auth.logout(session, clock, principal, request.cookies.get(SESSION_COOKIE, ""))
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=settings.session_cookie_secure,
    )
    return response


@router.get("/me")
def me(principal: PrincipalDep) -> UserOut:
    return UserOut.from_principal(principal)
