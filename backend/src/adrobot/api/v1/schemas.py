"""Typed Pydantic v2 request and response DTOs for `/api/v1` endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ApiResponseDto(BaseModel):
    """Base configuration for immutable API response DTOs."""

    model_config = ConfigDict(frozen=True, from_attributes=True)


class _ApiRequestDto(BaseModel):
    """Base configuration for strict API request DTOs."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SandboxDefaultsResponse(_ApiResponseDto):
    """Default Keitaro dictionary IDs and sandbox naming prefix."""

    domain_id: int
    group_id: int
    traffic_source_id: int
    campaign_prefix: str


class DomainResponse(_ApiResponseDto):
    """Keitaro domain dictionary option."""

    id: int
    name: str
    state: str | None = None
    is_ssl: bool | None = None
    default_campaign_id: int | None = None


class CampaignGroupResponse(_ApiResponseDto):
    """Keitaro campaign group dictionary option."""

    id: int
    name: str
    position: int | None = None
    type: str | None = None


class TrafficSourceResponse(_ApiResponseDto):
    """Keitaro traffic source dictionary option."""

    id: int
    name: str
    state: str | None = None


class DictionariesResponse(_ApiResponseDto):
    """Aggregated Keitaro dictionaries and sandbox defaults."""

    domains: list[DomainResponse]
    groups: list[CampaignGroupResponse]
    traffic_sources: list[TrafficSourceResponse]
    defaults: SandboxDefaultsResponse


class OfferResponse(_ApiResponseDto):
    """Keitaro offer entry returned by offer search."""

    id: int
    name: str
    group_id: int | None = None
    state: str | None = None
    payout_value: float | None = None
    payout_currency: str | None = None


class CreateCampaignRequest(_ApiRequestDto):
    """Payload to create a 2-stream campaign in Keitaro and local DB."""

    name: str = Field(min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=100)
    geo: list[str] | str = Field(default_factory=lambda: ["AU", "MX"])
    initial_offer_id: int = Field(gt=0)
    domain_id: int | None = Field(default=None, gt=0)
    group_id: int | None = Field(default=None, gt=0)
    traffic_source_id: int | None = Field(default=None, gt=0)


class AddStreamOfferRequest(_ApiRequestDto):
    """Payload to stage an offer onto a stream."""

    offer_id: int = Field(gt=0)
    offer_name: str = Field(default="", max_length=255)


class PinOfferRequest(_ApiRequestDto):
    """Optional payload to pin an offer to a specific share (1..100) or toggle pin."""

    share: int | None = None


class StreamOfferResponse(_ApiResponseDto):
    """Staged stream offer state."""

    id: int
    stream_id: int
    keitaro_offer_id: int
    offer_name: str
    share: int
    is_pinned: bool
    status: Literal["active", "removed"]
    is_published: bool
    published_share: int | None
    published_status: Literal["active", "removed"] | None
    created_at: datetime
    updated_at: datetime


class StreamResponse(_ApiResponseDto):
    """Staged stream state including push readiness flags."""

    id: int
    campaign_id: int
    keitaro_stream_id: int
    name: str
    position: int
    has_offers: bool
    is_dirty: bool
    can_push: bool
    validation_error: str | None
    offers: list[StreamOfferResponse]
    created_at: datetime
    updated_at: datetime


class CampaignSummaryResponse(_ApiResponseDto):
    """Locally tracked campaign summary."""

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


class CampaignDetailResponse(CampaignSummaryResponse):
    """Locally tracked campaign with ordered streams and staged offers."""

    streams: list[StreamResponse]
