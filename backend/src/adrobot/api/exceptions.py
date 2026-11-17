"""Global FastAPI exception handlers mapping domain errors to JSON responses."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from adrobot.api.schemas import ErrorBody, ErrorResponse
from adrobot.core.exceptions import AdrobotError

logger = logging.getLogger(__name__)


async def handle_adrobot_error(request: Request, exc: Exception) -> JSONResponse:
    """Translate domain exceptions into structured HTTP JSON responses."""
    if not isinstance(exc, AdrobotError):
        return await handle_unexpected_error(request, exc)

    logger.warning(
        "Domain error [%s] on %s %s: %s",
        exc.code,
        request.method,
        request.url.path,
        exc.message,
    )
    payload = ErrorResponse(
        error=ErrorBody(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Format FastAPI request validation errors into the shared error envelope."""
    details: dict[str, str] | None = None
    if isinstance(exc, RequestValidationError):
        details = {
            ".".join(str(part) for part in err.get("loc", ())): str(err.get("msg", "Invalid value"))
            for err in exc.errors()
        }

    logger.warning("Request validation error on %s %s", request.method, request.url.path)
    payload = ErrorResponse(
        error=ErrorBody(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=details,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=payload.model_dump(),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors without exposing internal details to clients."""
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, type(exc))
    payload = ErrorResponse(
        error=ErrorBody(
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload.model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to the FastAPI application."""
    app.add_exception_handler(AdrobotError, handle_adrobot_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
