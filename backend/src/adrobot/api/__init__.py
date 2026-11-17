"""HTTP API layer: routers, Pydantic DTOs, dependencies, and error handlers."""

from adrobot.api.exceptions import register_exception_handlers
from adrobot.api.routers import health_router
from adrobot.api.v1 import router as api_v1_router

__all__ = ["api_v1_router", "health_router", "register_exception_handlers"]
