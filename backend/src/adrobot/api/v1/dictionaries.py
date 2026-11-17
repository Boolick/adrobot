"""FastAPI router for Keitaro dictionary lookups and offer search."""

from fastapi import APIRouter, Query, status

from adrobot.api.dependencies import CampaignServiceDep
from adrobot.api.v1.schemas import DictionariesResponse, OfferResponse

router = APIRouter(tags=["Dictionaries"])


@router.get(
    "/dictionaries",
    response_model=DictionariesResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch Keitaro dictionaries and sandbox defaults",
)
async def get_dictionaries(service: CampaignServiceDep) -> DictionariesResponse:
    """Return domains, campaign groups, traffic sources, and sandbox defaults."""
    data = await service.get_dictionaries()
    return DictionariesResponse.model_validate(data)


@router.get(
    "/offers",
    response_model=list[OfferResponse],
    status_code=status.HTTP_200_OK,
    summary="Search Keitaro offers by ID or name",
)
async def search_offers(
    service: CampaignServiceDep,
    q: str | None = Query(default=None, description="Optional ID or name substring filter"),
) -> list[OfferResponse]:
    """Return Keitaro offers matching the optional search query."""
    offers = await service.search_offers(q)
    return [OfferResponse.model_validate(offer) for offer in offers]
