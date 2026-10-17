"""Sicherheitsbausteine: Passwort-Hash (Argon2), Session-Token, CSRF-Pflichtheader.

Die Demo-Authentifizierung ersetzt kein Identitätsmanagement für den Produktivbetrieb.
"""

import hashlib
import hmac
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from app.core.errors import ErrorBody

CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "fetch"
SESSION_COOKIE = "session"
API_PREFIX = "/api/"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TOKEN_BYTES = 32

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Hash für Scheinprüfungen unbekannter Konten (gleiche Rechenzeit wie bei bekannten Konten)."""
    return _hasher.hash(secrets.token_urlsafe(16))


def new_session_token() -> str:
    """Opaker Zufallstoken (32 Byte); nur der SHA-256-Hash wird gespeichert."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def install_csrf_guard(app: FastAPI) -> None:
    """Mutierende Requests unter `/api/` brauchen `X-Requested-With: fetch` (auch Login/Logout)."""

    @app.middleware("http")
    async def _csrf_guard(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method in MUTATING_METHODS
            and request.url.path.startswith(API_PREFIX)
            and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE
        ):
            body = ErrorBody(
                code="csrf_header_missing",
                message=f"Header {CSRF_HEADER}: {CSRF_HEADER_VALUE} is required",
            )
            return JSONResponse(status_code=403, content=body.model_dump())
        return await call_next(request)
