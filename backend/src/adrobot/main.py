"""FastAPI application entrypoint and lifecycle management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adrobot.api import api_v1_router, health_router, register_exception_handlers
from adrobot.core.config import get_settings
from adrobot.core.logging import configure_logging
from adrobot.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure logging on startup and dispose database connections on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_app()
