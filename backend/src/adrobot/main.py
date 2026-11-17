"""FastAPI application entrypoint and lifecycle management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adrobot.api import api_v1_router, health_router, register_exception_handlers
from adrobot.core.config import get_settings
from adrobot.core.exceptions import ConfigurationError
from adrobot.core.logging import configure_logging
from adrobot.db.session import engine
from adrobot.integrations.keitaro import KeitaroClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure logging, share one pooled KeitaroClient, and dispose resources on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    keitaro_client: KeitaroClient | None = None
    try:
        keitaro_client = KeitaroClient(
            base_url=settings.keitaro_api_url,
            api_key=settings.keitaro_api_key,
            timeout_seconds=settings.keitaro_timeout_seconds,
        )
    except ConfigurationError as exc:
        # Keep the API bootable (e.g. /health); Keitaro-backed routes will return a config error.
        logger.warning("Keitaro client not initialized: %s", exc.message)
    app.state.keitaro_client = keitaro_client
    try:
        yield
    finally:
        try:
            if keitaro_client is not None:
                await keitaro_client.aclose()
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
