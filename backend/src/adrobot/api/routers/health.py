"""Health check endpoint router."""

from fastapi import APIRouter, status

from adrobot.api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
)
async def health_check() -> HealthResponse:
    """Return service liveness status."""
    return HealthResponse(status="ok")
