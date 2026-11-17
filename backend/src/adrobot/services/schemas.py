"""Typed Pydantic v2 service-layer DTOs and ORM-to-DTO mappers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from adrobot.db.models import Campaign, CampaignStream, OfferStatus, StreamOffer
from adrobot.services.weights import validate_stream_for_push


class _ServiceDto(BaseModel):
    """Base configuration for immutable service DTOs."""

    model_config = ConfigDict(frozen=True)


class SandboxDefaultsData(_ServiceDto):
    """Sandbox defaults exposed alongside fetched Keitaro dictionaries."""

    domain_id: int
    group_id: int
    traffic_source_id: int
    campaign_prefix: str


class DomainData(_ServiceDto):
    """Keitaro domain dictionary entry."""

    id: int
    name: str
    state: str | None = None
    is_ssl: bool | None = None
    default_campaign_id: int | None = None


class CampaignGroupData(_ServiceDto):
    """Keitaro campaign group dictionary entry."""

    id: int
    name: str
    position: int | None = None
    type: str | None = None


class TrafficSourceData(_ServiceDto):
    """Keitaro traffic source dictionary entry."""

    id: int
    name: str
    state: str | None = None


class OfferData(_ServiceDto):
    """Keitaro offer search entry."""

    id: int
    name: str
    group_id: int | None = None
    state: str | None = None
    payout_value: float | None = None
    payout_currency: str | None = None


class DictionariesData(_ServiceDto):
    """Aggregated Keitaro dictionaries and sandbox defaults."""

    domains: list[DomainData]
    groups: list[CampaignGroupData]
    traffic_sources: list[TrafficSourceData]
    defaults: SandboxDefaultsData


class StreamOfferData(_ServiceDto):
    """Staged stream offer representation."""

    id: int
    stream_id: int
    keitaro_offer_id: int
    offer_name: str
    share: int
    is_pinned: bool
    status: OfferStatus
    is_published: bool
    published_share: int | None
    published_status: OfferStatus | None
    created_at: datetime
    updated_at: datetime


class StreamData(_ServiceDto):
    """Staged campaign stream representation with push readiness flags."""

    id: int
    campaign_id: int
    keitaro_stream_id: int
    name: str
    position: int
    has_offers: bool
    is_dirty: bool
    can_push: bool
    validation_error: str | None
    offers: list[StreamOfferData]
    created_at: datetime
    updated_at: datetime


class CampaignSummaryData(_ServiceDto):
    """Tracked campaign summary row."""

    id: int
    keitaro_campaign_id: int
    name: str
    alias: str | None
    geo: list[str]
    domain_id: int | None
    group_id: int | None
    source_id: int | None
    created_at: datetime
    updated_at: datetime


class CampaignDetailData(CampaignSummaryData):
    """Tracked campaign with ordered streams and staged offers."""

    streams: list[StreamData]


def _coerce_offer_status(value: str | None) -> OfferStatus:
    """Normalize persisted offer status strings to the OfferStatus literal."""
    return "removed" if value == "removed" else "active"


def stream_offer_to_data(offer: StreamOffer) -> StreamOfferData:
    """Map a StreamOffer ORM instance to an immutable StreamOfferData DTO."""
    published_status: OfferStatus | None = (
        _coerce_offer_status(offer.published_status) if offer.published_status is not None else None
    )
    return StreamOfferData(
        id=offer.id,
        stream_id=offer.stream_id,
        keitaro_offer_id=offer.keitaro_offer_id,
        offer_name=offer.offer_name,
        share=offer.share,
        is_pinned=offer.is_pinned,
        status=_coerce_offer_status(offer.status),
        is_published=offer.is_published,
        published_share=offer.published_share,
        published_status=published_status,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


def stream_to_data(stream: CampaignStream) -> StreamData:
    """Map a CampaignStream ORM instance (with loaded offers) to a StreamData DTO."""
    ordered_offers = sorted(
        stream.offers,
        key=lambda o: (0 if o.status == "active" else 1, o.id),
    )
    if stream.has_offers:
        can_push, validation_error = validate_stream_for_push(ordered_offers)
    else:
        can_push, validation_error = False, None

    return StreamData(
        id=stream.id,
        campaign_id=stream.campaign_id,
        keitaro_stream_id=stream.keitaro_stream_id,
        name=stream.name,
        position=stream.position,
        has_offers=stream.has_offers,
        is_dirty=stream.is_dirty,
        can_push=can_push,
        validation_error=validation_error,
        offers=[stream_offer_to_data(o) for o in ordered_offers],
        created_at=stream.created_at,
        updated_at=stream.updated_at,
    )


def campaign_to_summary(campaign: Campaign) -> CampaignSummaryData:
    """Map a Campaign ORM instance to a CampaignSummaryData DTO."""
    geo_codes = [part.strip() for part in campaign.geo.split(",") if part.strip()]
    return CampaignSummaryData(
        id=campaign.id,
        keitaro_campaign_id=campaign.keitaro_campaign_id,
        name=campaign.name,
        alias=campaign.alias,
        geo=geo_codes,
        domain_id=campaign.domain_id,
        group_id=campaign.group_id,
        source_id=campaign.source_id,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def campaign_to_detail(campaign: Campaign) -> CampaignDetailData:
    """Map a Campaign ORM instance (with loaded streams and offers) to CampaignDetailData."""
    summary = campaign_to_summary(campaign)
    ordered_streams = sorted(campaign.streams, key=lambda s: (s.position, s.id))
    return CampaignDetailData(
        **summary.model_dump(),
        streams=[stream_to_data(s) for s in ordered_streams],
    )
