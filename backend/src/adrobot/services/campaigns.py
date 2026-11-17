"""Application service for Keitaro dictionaries, offer search, and campaign creation."""

import asyncio
import logging
import re
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.core.config import Settings
from adrobot.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from adrobot.core.locks import campaign_name_locks
from adrobot.core.tasks import run_shielded
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
        session_factory: async_sessionmaker[AsyncSession],
        keitaro: KeitaroClient,
        settings: Settings,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
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

        # Run the whole Keitaro + DB workflow in a shielded task: a client disconnect must not
        # abandon the flow half-way (orphaned Keitaro campaign without a local record).
        campaign_id = await run_shielded(
            self._provision_campaign(
                name=validated_name,
                alias=resolved_alias,
                geo_list=geo_list,
                initial_offer_id=initial_offer_id,
                domain_id=resolved_domain_id,
                group_id=resolved_group_id,
                source_id=resolved_source_id,
            ),
            name=f"create_campaign:{validated_name}",
        )
        return await self.get_campaign_detail(campaign_id)

    async def _provision_campaign(
        self,
        *,
        name: str,
        alias: str | None,
        geo_list: list[str],
        initial_offer_id: int,
        domain_id: int,
        group_id: int,
        source_id: int,
    ) -> int:
        """Create campaign + 2 streams in Keitaro and persist locally; compensate on failure.

        Uses its own DB session (the request session may be closed if the client disconnects)
        and serializes concurrent requests for the same campaign name.
        """
        async with campaign_name_locks.acquire(name), self._session_factory() as session:
            campaigns = CampaignRepository(session)
            streams = StreamRepository(session)

            async with session.begin():
                existing = await campaigns.get_by_name(name)
            if existing is not None:
                raise ConflictError(
                    f"Campaign {name!r} already exists.",
                    details={"name": name},
                )

            kt_campaign = await self._keitaro.create_campaign(
                KeitaroCreateCampaignRequest(
                    name=name,
                    alias=alias,
                    type="position",
                    state="active",
                    cost_type="CPC",
                    domain_id=domain_id,
                    group_id=group_id,
                    traffic_source_id=source_id,
                )
            )

            flow1_id: int | None = None
            flow2_id: int | None = None
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
                flow1_id = kt_flow1.id
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
                flow2_id = kt_flow2.id

                async with session.begin():
                    campaign = await campaigns.create(
                        keitaro_campaign_id=kt_campaign.id,
                        name=kt_campaign.name,
                        alias=kt_campaign.alias if kt_campaign.alias is not None else alias,
                        geo=",".join(geo_list),
                        domain_id=domain_id,
                        group_id=group_id,
                        source_id=source_id,
                    )
                    await streams.create_stream(
                        campaign_id=campaign.id,
                        keitaro_stream_id=kt_flow1.id,
                        name=kt_flow1.name,
                        position=kt_flow1.position,
                        has_offers=False,
                        is_dirty=False,
                    )
                    flow2 = await streams.create_stream(
                        campaign_id=campaign.id,
                        keitaro_stream_id=kt_flow2.id,
                        name=kt_flow2.name,
                        position=kt_flow2.position,
                        has_offers=True,
                        is_dirty=False,
                    )
                    await streams.create_offer(
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
                    local_campaign_id = campaign.id
            except BaseException:
                logger.error(
                    "Campaign provisioning failed after Keitaro campaign creation; compensating "
                    "(keitaro_campaign_id=%s, flow1_id=%s, flow2_id=%s)",
                    kt_campaign.id,
                    flow1_id,
                    flow2_id,
                )
                await self._delete_keitaro_campaign_best_effort(kt_campaign.id)
                raise
            return local_campaign_id

    async def _delete_keitaro_campaign_best_effort(self, keitaro_campaign_id: int) -> None:
        """Delete an orphaned Keitaro campaign; log CRITICAL (never raise) if cleanup fails."""
        try:
            await self._keitaro.delete_campaign(keitaro_campaign_id)
        except Exception:
            logger.critical(
                "Failed to delete orphaned Keitaro campaign; manual cleanup required "
                "(keitaro_campaign_id=%s)",
                keitaro_campaign_id,
                exc_info=True,
            )
