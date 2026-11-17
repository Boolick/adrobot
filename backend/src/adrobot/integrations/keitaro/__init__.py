"""Keitaro Admin API integration package."""

from adrobot.integrations.keitaro.client import KeitaroClient
from adrobot.integrations.keitaro.schemas import (
    KeitaroCampaign,
    KeitaroCampaignGroup,
    KeitaroCreateCampaignRequest,
    KeitaroCreateStreamRequest,
    KeitaroDomain,
    KeitaroOffer,
    KeitaroStream,
    KeitaroStreamFilter,
    KeitaroStreamOfferItem,
    KeitaroStreamOfferResponse,
    KeitaroTrafficSource,
    KeitaroUpdateStreamOffersRequest,
)

__all__ = [
    "KeitaroCampaign",
    "KeitaroCampaignGroup",
    "KeitaroClient",
    "KeitaroCreateCampaignRequest",
    "KeitaroCreateStreamRequest",
    "KeitaroDomain",
    "KeitaroOffer",
    "KeitaroStream",
    "KeitaroStreamFilter",
    "KeitaroStreamOfferItem",
    "KeitaroStreamOfferResponse",
    "KeitaroTrafficSource",
    "KeitaroUpdateStreamOffersRequest",
]
