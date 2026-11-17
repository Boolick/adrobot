"""FastAPI router for campaign listing, creation, details, and stream sync."""

from fastapi import APIRouter, status

from adrobot.api.dependencies import CampaignServiceDep, StreamEditorServiceDep
from adrobot.api.v1.schemas import (
    CampaignDetailResponse,
    CampaignSummaryResponse,
    CreateCampaignRequest,
)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get(
    "",
    response_model=list[CampaignSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List locally tracked campaigns",
)
async def list_campaigns(service: CampaignServiceDep) -> list[CampaignSummaryResponse]:
    """Return locally tracked campaigns ordered newest first."""
    campaigns = await service.list_campaigns()
    return [CampaignSummaryResponse.model_validate(item) for item in campaigns]


@router.post(
    "",
    response_model=CampaignDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a 2-stream campaign in Keitaro and persist locally",
)
async def create_campaign(
    payload: CreateCampaignRequest,
    service: CampaignServiceDep,
) -> CampaignDetailResponse:
    """Create a campaign with Geo->Google and Offers streams in Keitaro."""
    detail = await service.create_campaign(
        name=payload.name,
        alias=payload.alias,
        geo=payload.geo,
        initial_offer_id=payload.initial_offer_id,
        domain_id=payload.domain_id,
        group_id=payload.group_id,
        traffic_source_id=payload.traffic_source_id,
    )
    return CampaignDetailResponse.model_validate(detail)


@router.get(
    "/{campaign_id}",
    response_model=CampaignDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get campaign details with staged streams and offers",
)
async def get_campaign_detail(
    campaign_id: int,
    service: CampaignServiceDep,
) -> CampaignDetailResponse:
    """Return campaign metadata, ordered streams, and staged offers."""
    detail = await service.get_campaign_detail(campaign_id)
    return CampaignDetailResponse.model_validate(detail)


@router.post(
    "/{campaign_id}/streams/fetch",
    response_model=CampaignDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch campaign streams from Keitaro into staging DB",
)
async def fetch_campaign_streams(
    campaign_id: int,
    service: StreamEditorServiceDep,
) -> CampaignDetailResponse:
    """Sync streams and offers from Keitaro into the local staging layer."""
    detail = await service.fetch_streams_from_kt(campaign_id)
    return CampaignDetailResponse.model_validate(detail)
