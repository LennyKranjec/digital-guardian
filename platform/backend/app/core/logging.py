"""Logging ohne Request-Bodies, Query-Strings, Antwortwerte oder Freitexte.

Protokolliert werden ausschließlich Methode, Pfad, Status, Dauer und Request-ID.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

access_logger = logging.getLogger("app.access")
_HANDLER_NAME = "app-stderr"


def configure_logging(level: str) -> None:
    """Idempotent: richtet genau einen Handler für den Namespace `app` ein."""
    root = logging.getLogger("app")
    root.setLevel(level.upper())
    if any(h.get_name() == _HANDLER_NAME for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)


def install_access_log(app: FastAPI) -> None:
    @app.middleware("http")
    async def _access_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        access_logger.info(
            "request method=%s path=%s status=%d duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            request_id,
        )
        return response
