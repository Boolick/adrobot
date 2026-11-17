"""Version 1 API router aggregation (`/api/v1`)."""

from fastapi import APIRouter

from adrobot.api.v1.campaigns import router as campaigns_router
from adrobot.api.v1.dictionaries import router as dictionaries_router
from adrobot.api.v1.streams import router as streams_router

router = APIRouter()
router.include_router(dictionaries_router)
router.include_router(campaigns_router)
router.include_router(streams_router)

__all__ = ["router"]
