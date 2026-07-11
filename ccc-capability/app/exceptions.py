from __future__ import annotations
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("capability.exceptions")


class CapabilityError(Exception):
    """Base class for all errors raised intentionally by this capability."""

    status_code: int = 500

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(CapabilityError):
    status_code = 404


class ValidationFailedError(CapabilityError):
    status_code = 422


class ConflictError(CapabilityError):
    status_code = 409


class DependencyUnavailableError(CapabilityError):
    """Raised when a required upstream dependency (DB, adapter) is down."""

    status_code = 503


def _error_body(error_type: str, message: str, detail: dict) -> dict:
    return {"error": {"type": error_type, "message": message, "detail": detail}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CapabilityError)
    async def handle_capability_error(request: Request, exc: CapabilityError):
        logger.warning(
            "capability_error",
            extra={"path": str(request.url), "error_type": type(exc).__name__, "error_message": exc.message},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(type(exc).__name__, exc.message, exc.detail),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        # This capability's own routers use FastAPI's built-in HTTPException
        # for straightforward not-found/bad-request cases (see app/crud.py).
        # That usage is correct and unchanged; this handler just makes sure
        # those responses come back in the same structured shape as
        # CapabilityError responses, so a consumer never has to branch on
        # which internal mechanism produced an error.
        logger.warning(
            "http_exception",
            extra={"path": str(request.url), "status_code": exc.status_code},
        )
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("HTTPException", str(exc.detail), detail),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        logger.warning(
            "request_validation_error",
            extra={"path": str(request.url), "errors": exc.errors()},
        )
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "RequestValidationError", "The request did not match the expected schema.", {"errors": exc.errors()}
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            extra={"path": str(request.url), "error_type": type(exc).__name__},
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content=_error_body("InternalServerError", "An unexpected error occurred.", {}),
        )
