"""Antwort-Header laut api.md v1.3: Security-Header und `Cache-Control: no-store`.

Bewusst ohne Abhängigkeit zu `errors`/`security`, damit beide Module sie nutzen können
(auch der Handler für unbehandelte Fehler, der außerhalb der Middleware-Kette antwortet).
"""

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

API_PREFIX = "/api/"

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
NO_STORE = "no-store"


def apply_response_headers(path: str, response: Response) -> None:
    """Setzt Security-Header immer; API-Antworten (auch Fehler) zusätzlich nie cachebar.

    `no-store` gilt für den gesamten `/api/`-Bereich: jede Antwort dort kann personenbezogene
    (synthetische) Daten oder Sitzungsinformationen enthalten; öffentliche Endpunkte wie
    `/meta` sind klein und brauchen kein Caching.
    """
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    if path.startswith(API_PREFIX):
        response.headers["Cache-Control"] = NO_STORE


def install_response_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _response_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        apply_response_headers(request.url.path, response)
        return response
