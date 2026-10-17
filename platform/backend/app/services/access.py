"""Rollenautorisierung (serverseitig). Objektbezogene Regeln liefert das Challenge-Paket.

Falsche Rolle: 403 `forbidden`. Richtige Rolle, aber fremdes Objekt: 404 `not_found`
(kein Existenzleck), siehe `not_found()`.
"""

from collections.abc import Iterable

from app.core.errors import ApiError
from app.services.auth import Principal


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Not found")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "Forbidden for this role")


def require_role(principal: Principal, roles: Iterable[str]) -> Principal:
    if principal.role not in set(roles):
        raise forbidden()
    return principal
