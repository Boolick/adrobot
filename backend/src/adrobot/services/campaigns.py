"""Application service for Keitaro dictionaries, offer search, and campaign creation."""

import asyncio
import logging
import re
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from adrobot.core.config import Settings
from adrobot.core.exceptions import DomainValidationError, NotFoundError
from adrobot.db.repositories import CampaignRepository, StreamRepository
from adrobot.integrations.keitaro import (
    KeitaroClient,
    KeitaroCreateCampaignRequest,
    KeitaroCreateStreamRequest,
    KeitaroStreamFilter,
    KeitaroStreamOfferItem,
)
from adrobot.services.schemas import (
    CampaignDetailData,
    CampaignGroupData,
    CampaignSummaryData,
    DictionariesData,
    DomainData,
    OfferData,
    SandboxDefaultsData,
    TrafficSourceData,
    campaign_to_detail,
    campaign_to_summary,
)

logger = logging.getLogger(__name__)

_CAMPAIGN_NAME_PATTERN = re.compile(r"^test_[a-zA-Z0-9_-]+$")
_ISO2_GEO_PATTERN = re.compile(r"^[A-Z]{2}$")
_FLOW1_REDIRECT_URL = "https://google.com/"


def validate_campaign_name(name: str) -> str:
    """Validate and normalize campaign names against sandbox prefix rules."""
    cleaned = name.strip()
    if not _CAMPAIGN_NAME_PATTERN.fullmatch(cleaned):
        raise DomainValidationError(
            "Campaign name must start with 'test_' and contain a valid suffix "
            "(matching ^test_[a-zA-Z0-9_-]+$).",
            details={"name": cleaned},
        )
    return cleaned


def normalize_geo_codes(raw_geo: Sequence[str] | str) -> list[str]:
    """Normalize and validate ISO 3166-1 alpha-2 country codes."""
    raw_items: Sequence[str] = raw_geo.split(",") if isinstance(raw_geo, str) else raw_geo
    normalized: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        code = item.strip().upper()
        if not code:
            continue
        if not _ISO2_GEO_PATTERN.fullmatch(code):
            raise DomainValidationError(
                f"Invalid GEO code {item!r}: expected 2-letter ISO country code (e.g., AU, MX).",
                details={"geo": item},
            )
        if code not in seen:
            seen.add(code)
            normalized.append(code)

    if not normalized:
        raise DomainValidationError(
            "At least one valid 2-letter ISO country code is required.",
            details={"geo": ""},
        )
    return normalized


class CampaignService:
    """Orchestrates dictionary lookups and 3-step Keitaro campaign creation."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        keitaro: KeitaroClient,
        settings: Settings,
    ) -> None:
        self._session = session
        self._keitaro = keitaro
        self._settings = settings
        self._campaigns = CampaignRepository(session)
        self._streams = StreamRepository(session)

    async def get_dictionaries(self) -> DictionariesData:
        """Fetch domains, campaign groups, and traffic sources concurrently with defaults."""
        domains, groups, sources = await asyncio.gather(
            self._keitaro.get_domains(),
            self._keitaro.get_campaign_groups(),
            self._keitaro.get_traffic_sources(),
        )
        return DictionariesData(
            domains=[
                DomainData(
                    id=d.id,
                    name=d.name,
                    state=d.state,
                    is_ssl=d.is_ssl,
                    default_campaign_id=d.default_campaign_id,
                )
                for d in domains
            ],
            groups=[
                CampaignGroupData(id=g.id, name=g.name, position=g.position, type=g.type)
                for g in groups
            ],
            traffic_sources=[
                TrafficSourceData(id=s.id, name=s.name, state=s.state) for s in sources
            ],
            defaults=SandboxDefaultsData(
                domain_id=self._settings.keitaro_default_domain_id,
                group_id=self._settings.keitaro_default_group_id,
                traffic_source_id=self._settings.keitaro_default_traffic_source_id,
                campaign_prefix=self._settings.keitaro_campaign_prefix,
            ),
        )

    async def search_offers(self, query: str | None = None) -> list[OfferData]:
        """Search Keitaro offers by ID or case-insensitive name substring."""
        offers = await self._keitaro.search_offers(query)
        return [
            OfferData(
                id=o.id,
                name=o.name,
                group_id=o.group_id,
                state=o.state,
                payout_value=o.payout_value,
                payout_currency=o.payout_currency,
            )
            for o in offers
        ]

    async def list_campaigns(self) -> list[CampaignSummaryData]:
        """Return locally tracked campaigns ordered newest-first."""
        campaigns = await self._campaigns.list_all()
        await self._session.commit()
        return [campaign_to_summary(c) for c in campaigns]

    async def get_campaign_detail(self, campaign_id: int) -> CampaignDetailData:
        """Return a tracked campaign with ordered streams and staged offers."""
        campaign = await self._campaigns.get_by_id_with_streams(campaign_id)
        if campaign is None:
            raise NotFoundError(
                f"Campaign {campaign_id} was not found.",
                details={"campaign_id": str(campaign_id)},
            )
        await self._session.commit()
        return campaign_to_detail(campaign)

    async def create_campaign(
        self,
        *,
        name: str,
        initial_offer_id: int,
        geo: Sequence[str] | str = ("AU", "MX"),
        alias: str | None = None,
        domain_id: int | None = None,
        group_id: int | None = None,
        traffic_source_id: int | None = None,
    ) -> CampaignDetailData:
        """Create a 2-stream campaign in Keitaro and persist tracking + staging records locally."""
        validated_name = validate_campaign_name(name)
        geo_list = normalize_geo_codes(geo)
        if initial_offer_id <= 0:
            raise DomainValidationError(
                "initial_offer_id must be a positive integer.",
                details={"initial_offer_id": str(initial_offer_id)},
            )

        cleaned_alias = alias.strip() if alias is not None else None
        resolved_alias = cleaned_alias if cleaned_alias else None
        resolved_domain_id = (
            domain_id if domain_id is not None else self._settings.keitaro_default_domain_id
        )
        resolved_group_id = (
            group_id if group_id is not None else self._settings.keitaro_default_group_id
        )
        resolved_source_id = (
            traffic_source_id
            if traffic_source_id is not None
            else self._settings.keitaro_default_traffic_source_id
        )
        for field_name, val in (
            ("domain_id", resolved_domain_id),
            ("group_id", resolved_group_id),
            ("traffic_source_id", resolved_source_id),
        ):
            if val <= 0:
                raise DomainValidationError(
                    f"{field_name} must be a positive integer.",
                    details={field_name: str(val)},
                )

        # Execute all Keitaro HTTP calls before opening any local SQLite write transaction.
        kt_campaign = await self._keitaro.create_campaign(
            KeitaroCreateCampaignRequest(
                name=validated_name,
                alias=resolved_alias,
                type="position",
                state="active",
                cost_type="CPC",
                domain_id=resolved_domain_id,
                group_id=resolved_group_id,
                traffic_source_id=resolved_source_id,
            )
        )

        try:
            kt_flow1 = await self._keitaro.create_stream(
                KeitaroCreateStreamRequest(
                    campaign_id=kt_campaign.id,
                    type="regular",
                    name="Geo -> Google",
                    position=1,
                    state="active",
                    stream_schema="redirect",
                    action_type="http",
                    action_payload=_FLOW1_REDIRECT_URL,
                    filters=[
                        KeitaroStreamFilter(
                            name="country",
                            mode="accept",
                            payload=geo_list,
                        )
                    ],
                )
            )
            kt_flow2 = await self._keitaro.create_stream(
                KeitaroCreateStreamRequest(
                    campaign_id=kt_campaign.id,
                    type="default",
                    name="Offers",
                    position=2,
                    state="active",
                    stream_schema="landings",
                    action_type="http",
                    offers=[
                        KeitaroStreamOfferItem(
                            offer_id=initial_offer_id,
                            share=100,
                            state="active",
                        )
                    ],
                )
            )
        except Exception:
            logger.error(
                "Stream creation failed after Keitaro campaign creation "
                "(keitaro_campaign_id=%s, name=%s)",
                kt_campaign.id,
                kt_campaign.name,
            )
            raise

        try:
            async with self._session.begin():
                campaign = await self._campaigns.create(
                    keitaro_campaign_id=kt_campaign.id,
                    name=kt_campaign.name,
                    alias=kt_campaign.alias if kt_campaign.alias is not None else resolved_alias,
                    geo=",".join(geo_list),
                    domain_id=resolved_domain_id,
                    group_id=resolved_group_id,
                    source_id=resolved_source_id,
                )
                await self._streams.create_stream(
                    campaign_id=campaign.id,
                    keitaro_stream_id=kt_flow1.id,
                    name=kt_flow1.name,
                    position=kt_flow1.position,
                    has_offers=False,
                    is_dirty=False,
                )
                flow2 = await self._streams.create_stream(
                    campaign_id=campaign.id,
                    keitaro_stream_id=kt_flow2.id,
                    name=kt_flow2.name,
                    position=kt_flow2.position,
                    has_offers=True,
                    is_dirty=False,
                )
                await self._streams.create_offer(
                    stream_id=flow2.id,
                    keitaro_offer_id=initial_offer_id,
                    offer_name=f"Offer #{initial_offer_id}",
                    share=100,
                    is_pinned=False,
                    status="active",
                    is_published=True,
                    published_share=100,
                    published_status="active",
                )
        except Exception:
            logger.critical(
                "Local DB persistence failed after Keitaro campaign creation "
                "(keitaro_campaign_id=%s, flow1_id=%s, flow2_id=%s)",
                kt_campaign.id,
                kt_flow1.id,
                kt_flow2.id,
            )
            raise

        return await self.get_campaign_detail(campaign.id)
