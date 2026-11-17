"""Async repository for CampaignStream and StreamOffer staging persistence."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adrobot.core.exceptions import ResourceConflictError, ResourceNotFoundError
from adrobot.db.models import CampaignStream, OfferStatus, StreamOffer


def _is_foreign_key_error(exc: IntegrityError) -> bool:
    """Return True if an IntegrityError originated from a foreign key violation."""
    if exc.orig is None:
        return False
    return "foreign key" in str(exc.orig).lower()


class StreamRepository:
    """Repository encapsulating async CRUD queries for CampaignStream and StreamOffer records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_stream(
        self,
        *,
        campaign_id: int,
        keitaro_stream_id: int,
        name: str,
        position: int = 1,
        has_offers: bool = False,
        is_dirty: bool = False,
    ) -> CampaignStream:
        """Add a CampaignStream and flush to populate DB-generated fields without committing."""
        stream = CampaignStream(
            campaign_id=campaign_id,
            keitaro_stream_id=keitaro_stream_id,
            name=name,
            position=position,
            has_offers=has_offers,
            is_dirty=is_dirty,
            offers=[],
        )
        self._session.add(stream)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_foreign_key_error(exc):
                raise ResourceNotFoundError(
                    f"Campaign with id={campaign_id} was not found.",
                    details={"campaign_id": str(campaign_id)},
                ) from exc
            raise ResourceConflictError(
                f"CampaignStream with keitaro_stream_id={keitaro_stream_id} already exists.",
                details={"keitaro_stream_id": str(keitaro_stream_id)},
            ) from exc
        return stream

    async def get_stream_by_id(self, stream_id: int) -> CampaignStream | None:
        """Return a CampaignStream with eagerly loaded offers by local ID, or None."""
        stmt = (
            select(CampaignStream)
            .where(CampaignStream.id == stream_id)
            .options(selectinload(CampaignStream.offers))
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_stream_by_keitaro_id(
        self,
        keitaro_stream_id: int,
        *,
        campaign_id: int | None = None,
    ) -> CampaignStream | None:
        """Return a CampaignStream with offers by Keitaro stream ID (optionally campaign-scoped)."""
        stmt = (
            select(CampaignStream)
            .where(CampaignStream.keitaro_stream_id == keitaro_stream_id)
            .options(selectinload(CampaignStream.offers))
            .execution_options(populate_existing=True)
        )
        if campaign_id is not None:
            stmt = stmt.where(CampaignStream.campaign_id == campaign_id)
        return await self._session.scalar(stmt)

    async def list_streams_by_campaign(self, campaign_id: int) -> Sequence[CampaignStream]:
        """Return all streams for a campaign ordered by position, with offers eagerly loaded."""
        stmt = (
            select(CampaignStream)
            .where(CampaignStream.campaign_id == campaign_id)
            .options(selectinload(CampaignStream.offers))
            .execution_options(populate_existing=True)
            .order_by(CampaignStream.position.asc(), CampaignStream.id.asc())
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def upsert_stream(
        self,
        *,
        campaign_id: int,
        keitaro_stream_id: int,
        name: str,
        position: int,
        has_offers: bool,
        is_dirty: bool | None = None,
    ) -> CampaignStream:
        """Create or update a CampaignStream keyed by keitaro_stream_id, with offers loaded."""
        existing = await self.get_stream_by_keitaro_id(keitaro_stream_id, campaign_id=campaign_id)
        if existing is None:
            return await self.create_stream(
                campaign_id=campaign_id,
                keitaro_stream_id=keitaro_stream_id,
                name=name,
                position=position,
                has_offers=has_offers,
                is_dirty=False if is_dirty is None else is_dirty,
            )

        existing.name = name
        existing.position = position
        existing.has_offers = has_offers
        if is_dirty is not None:
            existing.is_dirty = is_dirty

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_foreign_key_error(exc):
                raise ResourceNotFoundError(
                    f"Campaign with id={campaign_id} was not found.",
                    details={"campaign_id": str(campaign_id)},
                ) from exc
            raise ResourceConflictError(
                f"CampaignStream with keitaro_stream_id={keitaro_stream_id} conflicts.",
                details={"keitaro_stream_id": str(keitaro_stream_id)},
            ) from exc
        return existing

    async def set_stream_dirty(self, stream_id: int, *, is_dirty: bool) -> CampaignStream:
        """Update a stream's is_dirty staging flag and flush without committing."""
        stream = await self.get_stream_by_id(stream_id)
        if stream is None:
            raise ResourceNotFoundError(
                f"CampaignStream with id={stream_id} was not found.",
                details={"stream_id": str(stream_id)},
            )
        stream.is_dirty = is_dirty
        await self._session.flush()
        return stream

    async def create_offer(
        self,
        *,
        stream_id: int,
        keitaro_offer_id: int,
        offer_name: str = "",
        share: int = 0,
        is_pinned: bool = False,
        status: OfferStatus = "active",
        is_published: bool = True,
        published_share: int | None = None,
        published_status: OfferStatus | None = None,
    ) -> StreamOffer:
        """Add a StreamOffer and flush without committing."""
        offer = StreamOffer(
            stream_id=stream_id,
            keitaro_offer_id=keitaro_offer_id,
            offer_name=offer_name,
            share=share,
            is_pinned=is_pinned,
            status=status,
            is_published=is_published,
            published_share=published_share,
            published_status=published_status,
        )
        self._session.add(offer)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_foreign_key_error(exc):
                raise ResourceNotFoundError(
                    f"CampaignStream with id={stream_id} was not found.",
                    details={"stream_id": str(stream_id)},
                ) from exc
            raise ResourceConflictError(
                f"Offer {keitaro_offer_id} already exists in stream {stream_id}.",
                details={
                    "stream_id": str(stream_id),
                    "keitaro_offer_id": str(keitaro_offer_id),
                },
            ) from exc
        return offer

    async def get_offer(self, stream_id: int, keitaro_offer_id: int) -> StreamOffer | None:
        """Return a StreamOffer by (stream_id, keitaro_offer_id), or None if not found."""
        stmt = select(StreamOffer).where(
            StreamOffer.stream_id == stream_id,
            StreamOffer.keitaro_offer_id == keitaro_offer_id,
        )
        return await self._session.scalar(stmt)

    async def list_offers_by_stream(
        self,
        stream_id: int,
        *,
        status: OfferStatus | None = None,
    ) -> Sequence[StreamOffer]:
        """Return StreamOffer rows for a stream ordered by ID, optionally filtered by status."""
        stmt = select(StreamOffer).where(StreamOffer.stream_id == stream_id)
        if status is not None:
            stmt = stmt.where(StreamOffer.status == status)
        stmt = stmt.order_by(StreamOffer.id.asc())
        result = await self._session.scalars(stmt)
        return result.all()

    async def upsert_offer(
        self,
        *,
        stream_id: int,
        keitaro_offer_id: int,
        offer_name: str = "",
        share: int = 0,
        is_pinned: bool = False,
        status: OfferStatus = "active",
        is_published: bool = True,
        published_share: int | None = None,
        published_status: OfferStatus | None = None,
    ) -> StreamOffer:
        """Create or update a StreamOffer keyed by (stream_id, keitaro_offer_id)."""
        existing = await self.get_offer(stream_id, keitaro_offer_id)
        if existing is None:
            return await self.create_offer(
                stream_id=stream_id,
                keitaro_offer_id=keitaro_offer_id,
                offer_name=offer_name,
                share=share,
                is_pinned=is_pinned,
                status=status,
                is_published=is_published,
                published_share=published_share,
                published_status=published_status,
            )

        existing.offer_name = offer_name
        existing.share = share
        existing.is_pinned = is_pinned
        existing.status = status
        existing.is_published = is_published
        existing.published_share = published_share
        existing.published_status = published_status
        await self._session.flush()
        return existing

    async def delete_unpublished_offers(self, stream_id: int) -> int:
        """Delete all local offers in a stream with is_published == False and return count."""
        stmt = (
            select(StreamOffer)
            .where(
                StreamOffer.stream_id == stream_id,
                StreamOffer.is_published.is_(False),
            )
            .order_by(StreamOffer.id.asc())
        )
        unpublished = (await self._session.scalars(stmt)).all()
        for offer in unpublished:
            await self._session.delete(offer)
        if unpublished:
            await self._session.flush()
        return len(unpublished)

    async def delete_offer(self, stream_id: int, keitaro_offer_id: int) -> bool:
        """Delete a single StreamOffer by (stream_id, keitaro_offer_id); return True if deleted."""
        offer = await self.get_offer(stream_id, keitaro_offer_id)
        if offer is None:
            return False
        await self._session.delete(offer)
        await self._session.flush()
        return True
