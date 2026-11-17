"""FastAPI router for stream offer staging (ADD, REMOVE, PIN, REBALANCE, CANCEL, PUSH).

All route handlers delegate business rules and transactions to StreamEditorService.
"""

from typing import Annotated

from fastapi import APIRouter, Body, status

from adrobot.api.dependencies import StreamEditorServiceDep
from adrobot.api.v1.schemas import AddStreamOfferRequest, PinOfferRequest, StreamResponse

router = APIRouter(prefix="/streams", tags=["Stream Editor"])


@router.post(
    "/{stream_id}/offers",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Stage an offer onto a stream",
)
async def add_stream_offer(
    stream_id: int,
    payload: AddStreamOfferRequest,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Add or reactivate an offer in the local staging table and recalculate shares."""
    stream = await service.add_offer(stream_id, payload.offer_id, payload.offer_name)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/offers/{offer_id}/remove",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark a staged stream offer as removed",
)
async def remove_stream_offer(
    stream_id: int,
    offer_id: int,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Archive an active offer locally (`status='removed'`) and redistribute shares."""
    stream = await service.remove_offer(stream_id, offer_id)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/offers/{offer_id}/bring-back",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore a locally removed stream offer",
)
async def bring_back_stream_offer(
    stream_id: int,
    offer_id: int,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Restore an archived offer back to active status and recalculate shares."""
    stream = await service.bring_back_offer(stream_id, offer_id)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/offers/{offer_id}/pin",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle pin or set explicit pinned share for an active offer",
)
async def pin_stream_offer(
    stream_id: int,
    offer_id: int,
    service: StreamEditorServiceDep,
    payload: Annotated[PinOfferRequest | None, Body()] = None,
) -> StreamResponse:
    """Toggle pin status or pin to a specific share (1..100) and recalculate shares."""
    share = payload.share if payload is not None else None
    stream = await service.toggle_pin(stream_id, offer_id, share=share)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/rebalance",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Normalize active offer shares to 100%",
)
async def rebalance_stream_offers(
    stream_id: int,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Unpin all active offers and redistribute shares evenly so they sum to 100%."""
    stream = await service.rebalance_stream(stream_id)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/cancel",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel staged local edits for a stream",
)
async def cancel_stream_changes(
    stream_id: int,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Delete unpublished staged offers and restore published offer snapshots."""
    stream = await service.cancel_changes(stream_id)
    return StreamResponse.model_validate(stream)


@router.post(
    "/{stream_id}/push",
    response_model=StreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Push active staged offers to Keitaro",
)
async def push_stream_to_keitaro(
    stream_id: int,
    service: StreamEditorServiceDep,
) -> StreamResponse:
    """Validate active offers and push them to Keitaro via PUT streams/{id}."""
    stream = await service.push_to_kt(stream_id)
    return StreamResponse.model_validate(stream)
