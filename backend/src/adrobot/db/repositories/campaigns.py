"""Async repository for Campaign ORM persistence operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adrobot.core.exceptions import ResourceConflictError
from adrobot.db.models import Campaign, CampaignStream


class CampaignRepository:
    """Repository encapsulating async CRUD queries for Campaign records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        keitaro_campaign_id: int,
        name: str,
        geo: str,
        alias: str | None = None,
        domain_id: int | None = None,
        group_id: int | None = None,
        source_id: int | None = None,
    ) -> Campaign:
        """Add a Campaign and flush to populate DB-generated fields without committing."""
        campaign = Campaign(
            keitaro_campaign_id=keitaro_campaign_id,
            name=name,
            alias=alias,
            geo=geo,
            domain_id=domain_id,
            group_id=group_id,
            source_id=source_id,
        )
        self._session.add(campaign)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ResourceConflictError(
                f"Campaign with keitaro_campaign_id={keitaro_campaign_id} already exists.",
                details={"keitaro_campaign_id": str(keitaro_campaign_id)},
            ) from exc
        return campaign

    async def get_by_id(self, campaign_id: int) -> Campaign | None:
        """Return a Campaign by its local primary key ID, or None if not found."""
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        return await self._session.scalar(stmt)

    async def get_by_id_with_streams(self, campaign_id: int) -> Campaign | None:
        """Return a Campaign with eagerly loaded streams and stream offers, or None."""
        stmt = (
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .options(selectinload(Campaign.streams).selectinload(CampaignStream.offers))
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_by_keitaro_id(self, keitaro_campaign_id: int) -> Campaign | None:
        """Return a Campaign by its Keitaro campaign ID, or None if not found."""
        stmt = select(Campaign).where(Campaign.keitaro_campaign_id == keitaro_campaign_id)
        return await self._session.scalar(stmt)

    async def get_by_keitaro_id_with_streams(self, keitaro_campaign_id: int) -> Campaign | None:
        """Return a Campaign by Keitaro ID with eagerly loaded streams and offers, or None."""
        stmt = (
            select(Campaign)
            .where(Campaign.keitaro_campaign_id == keitaro_campaign_id)
            .options(selectinload(Campaign.streams).selectinload(CampaignStream.offers))
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def list_all(self) -> Sequence[Campaign]:
        """Return all Campaigns ordered by newest created_at (and id tiebreaker)."""
        stmt = select(Campaign).order_by(Campaign.created_at.desc(), Campaign.id.desc())
        result = await self._session.scalars(stmt)
        return result.all()
