"""Auth-Dependencies für Routen: Hauptakteur und Rollenprüfung (immer serverseitig).

Rollen sind Namen aus der Registry; `require_roles("admin")` ist generisch. Challenge-Pakete bilden
eigene Aliase (z. B. `ReviewerDep = Annotated[Principal, Depends(require_roles("reviewer"))]`).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.clock import ClockDep
from app.core.deps import RegistryDep, SessionDep
from app.core.errors import ApiError
from app.core.security import SESSION_COOKIE
from app.services import access, auth
from app.services.auth import Principal


def current_principal(
    request: Request, session: SessionDep, clock: ClockDep, registry: RegistryDep
) -> Principal:
    principal = auth.authenticate(
        session, clock, request.cookies.get(SESSION_COOKIE), registry.resolve_subject
    )
    if principal is None:
        raise ApiError(401, "unauthenticated", "Authentication required")
    return principal


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency-Fabrik: falsche Rolle → 403 `forbidden`, nicht eingeloggt → 401."""

    def dependency(principal: PrincipalDep) -> Principal:
        return access.require_role(principal, roles)

    return dependency


AdminDep = Annotated[Principal, Depends(require_roles("admin"))]
