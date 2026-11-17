"""Strict Pydantic v2 schemas for Keitaro Admin API requests and responses."""

from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field, field_validator


def _empty_str_to_none(value: object) -> object:
    """Coerce blank string values returned by Keitaro into None for optional numeric fields."""
    if value == "":
        return None
    return value


OptionalInt = Annotated[int | None, BeforeValidator(_empty_str_to_none)]
OptionalFloat = Annotated[float | None, BeforeValidator(_empty_str_to_none)]


class _KeitaroResponseModel(BaseModel):
    """Base configuration for tolerant parsing of external Keitaro API responses."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class _KeitaroRequestModel(BaseModel):
    """Base configuration for strict serialization of outgoing Keitaro API payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class KeitaroDomain(_KeitaroResponseModel):
    """Domain dictionary entry returned by GET domains."""

    id: int
    name: str
    state: str | None = None
    is_ssl: bool | None = None
    default_campaign_id: OptionalInt = None


class KeitaroCampaignGroup(_KeitaroResponseModel):
    """Campaign group dictionary entry returned by GET groups?type=campaigns."""

    id: int
    name: str
    position: OptionalInt = None
    type: str | None = None


class KeitaroTrafficSource(_KeitaroResponseModel):
    """Traffic source dictionary entry returned by GET traffic_sources."""

    id: int
    name: str
    state: str | None = None


class KeitaroOffer(_KeitaroResponseModel):
    """Offer dictionary entry returned by GET offers."""

    id: int
    name: str
    group_id: OptionalInt = None
    state: str | None = None
    payout_value: OptionalFloat = None
    payout_currency: str | None = None


class KeitaroCreateCampaignRequest(_KeitaroRequestModel):
    """Request payload for POST campaigns."""

    name: str = Field(min_length=1, max_length=255)
    alias: str | None = Field(default=None, min_length=1, max_length=100)
    type: Literal["position", "weight"] = "position"
    state: Literal["active", "disabled"] = "active"
    cost_type: str = Field(default="CPC", min_length=1, max_length=32)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)


class KeitaroCampaign(_KeitaroResponseModel):
    """Campaign resource returned by Keitaro Admin API."""

    id: int
    name: str
    alias: str | None = None
    type: str | None = None
    state: str | None = None
    cost_type: str | None = None
    domain_id: OptionalInt = None
    group_id: OptionalInt = None
    traffic_source_id: OptionalInt = None


class KeitaroStreamFilter(_KeitaroRequestModel):
    """Stream filter definition used in POST streams."""

    name: str = Field(min_length=1)
    mode: Literal["accept", "reject"] = "accept"
    payload: list[str] = Field(min_length=1)


class KeitaroStreamOfferItem(_KeitaroRequestModel):
    """Offer weight allocation sent to POST streams or PUT streams/{id}."""

    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)
    state: Literal["active", "disabled"] = "active"


class KeitaroStreamOfferResponse(_KeitaroResponseModel):
    """Offer entry nested inside a Keitaro stream response."""

    offer_id: int
    share: int
    state: str = "active"
    id: OptionalInt = None
    offer_name: str | None = None
    name: str | None = None


class KeitaroCreateStreamRequest(_KeitaroRequestModel):
    """Request payload for POST streams (Flow 1 redirect or Flow 2 offers)."""

    campaign_id: int = Field(gt=0)
    type: Literal["regular", "default", "forced"] = "regular"
    name: str = Field(min_length=1, max_length=255)
    position: int = Field(ge=1)
    state: Literal["active", "disabled"] = "active"
    stream_schema: Literal["redirect", "landings"] = Field(
        validation_alias=AliasChoices("stream_schema", "schema"),
        serialization_alias="schema",
    )
    action_type: str = Field(default="http", min_length=1)
    action_payload: str | None = None
    filters: list[KeitaroStreamFilter] | None = None
    offers: list[KeitaroStreamOfferItem] | None = None


class KeitaroUpdateStreamOffersRequest(_KeitaroRequestModel):
    """Request payload for PUT streams/{id} when syncing active stream offers."""

    offers: list[KeitaroStreamOfferItem]


class KeitaroStream(_KeitaroResponseModel):
    """Stream resource returned by POST streams, GET campaigns/{id}/streams, or PUT streams/{id}."""

    id: int
    campaign_id: OptionalInt = None
    type: str | None = None
    name: str
    position: int = 1
    state: str | None = None
    stream_schema: str | None = Field(
        default=None,
        validation_alias=AliasChoices("stream_schema", "schema"),
        serialization_alias="schema",
    )
    action_type: str | None = None
    action_payload: str | None = None
    offers: list[KeitaroStreamOfferResponse] = Field(
        default_factory=list[KeitaroStreamOfferResponse]
    )

    @field_validator("offers", mode="before")
    @classmethod
    def coerce_none_offers(cls, value: object) -> object:
        """Normalize null offers lists from Keitaro into an empty list."""
        if value is None:
            return []
        return value
