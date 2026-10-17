"""Einheitliches Fehlerformat (docs/contracts/api.md): code / message / field_errors."""

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.headers import apply_response_headers

logger = logging.getLogger("app.errors")

_STATUS_CODES = {
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
}
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    field_errors: list[FieldError] = []


class ApiError(Exception):
    """Fachlich erwarteter Fehler mit stabilem `code`."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: Sequence[FieldError] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = list(field_errors)


def _respond(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(ApiError, exc)
    body = ErrorBody(code=exc.code, message=exc.message, field_errors=exc.field_errors)
    return _respond(exc.status_code, body)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "HTTP error"
    return _respond(exc.status_code, ErrorBody(code=code, message=message))


def _field_errors(errors: Sequence[Any]) -> list[FieldError]:
    """Übernimmt nur Ort, Typ und Meldung; niemals den eingegebenen Wert (`input`)."""
    result: list[FieldError] = []
    for err in errors:
        loc = [str(part) for part in err.get("loc", ())]
        if loc and loc[0] in _LOC_PREFIXES:
            loc = loc[1:]
        result.append(
            FieldError(
                field=".".join(loc),
                code=str(err.get("type", "invalid")),
                message=str(err.get("msg", "Invalid value")),
            )
        )
    return result


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    body = ErrorBody(
        code="validation_failed",
        message="Request validation failed",
        field_errors=_field_errors(exc.errors()),
    )
    return _respond(422, body)


async def _db_error(request: Request, exc: Exception) -> JSONResponse:
    # Verbindung/Schema fehlt (z. B. nicht migriert): Betriebsfehler, nie 500 (api.md v1.4).
    logger.error(
        "database error method=%s path=%s error=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return _respond(503, ErrorBody(code="db_unavailable", message="Database is not available"))


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled error method=%s path=%s error=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    response = _respond(500, ErrorBody(code="internal_error", message="Internal server error"))
    # Dieser Handler antwortet außerhalb der Middleware-Kette; Header daher hier setzen.
    apply_response_headers(request.url.path, response)
    return response


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(OperationalError, _db_error)
    app.add_exception_handler(Exception, _unhandled_error)
