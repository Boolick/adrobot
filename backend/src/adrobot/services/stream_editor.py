"""Application service for local stream offer staging and Keitaro synchronization."""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from adrobot.core.locks import campaign_locks, stream_locks
from adrobot.core.tasks import run_shielded
from adrobot.db.models import CampaignStream, StreamOffer
from adrobot.db.repositories import CampaignRepository, StreamRepository
from adrobot.integrations.keitaro import KeitaroClient, KeitaroStreamOfferItem
from adrobot.services.schemas import (
    CampaignDetailData,
    StreamData,
    campaign_to_detail,
    stream_to_data,
)
from adrobot.services.weights import recalculate_shares, validate_stream_for_push

logger = logging.getLogger(__name__)


@dataclass
class _KtOfferSnapshot:
    """Aggregated view of one offer id inside a Keitaro stream response."""

    name: str
    entries: int = 0
    active_share: int = 0


class StreamEditorService:
    """Manages local stream/offer staging mutations, rollback (CANCEL), and sync with Keitaro."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
        keitaro: KeitaroClient,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._keitaro = keitaro
        self._campaigns = CampaignRepository(session)
        self._streams = StreamRepository(session)

    async def _get_editable_stream(self, stream_id: int) -> CampaignStream:
        """Load a stream inside the current transaction and validate it supports offer editing."""
        stream = await self._streams.get_stream_by_id(stream_id)
        if stream is None:
            raise NotFoundError(
                f"Stream {stream_id} was not found.",
                details={"stream_id": str(stream_id)},
            )
        if not stream.has_offers:
            raise DomainValidationError(
                "This stream does not manage offers and cannot be edited here.",
                details={"stream_id": str(stream_id)},
            )
        return stream

    @staticmethod
    def _find_offer(stream: CampaignStream, offer_id: int) -> StreamOffer:
        """Find a staged offer by keitaro_offer_id within a loaded stream."""
        for offer in stream.offers:
            if offer.keitaro_offer_id == offer_id:
                return offer
        raise NotFoundError(
            f"Offer {offer_id} was not found in stream {stream.id}.",
            details={"stream_id": str(stream.id), "offer_id": str(offer_id)},
        )

    async def _reload_stream_data(self, stream_id: int) -> StreamData:
        """Reload a stream with offers after commit and serialize to StreamData."""
        refreshed = await self._streams.get_stream_by_id(stream_id)
        if refreshed is None:
            raise NotFoundError(
                f"Stream {stream_id} was not found.",
                details={"stream_id": str(stream_id)},
            )
        await self._session.commit()
        return stream_to_data(refreshed)

    async def fetch_streams_from_kt(self, campaign_id: int) -> CampaignDetailData:
        """Sync campaign streams and offer snapshots from Keitaro into local staging tables."""
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(campaign_locks.acquire(campaign_id))
            return await self._fetch_streams_locked(campaign_id, stack)

    async def _fetch_streams_locked(
        self,
        campaign_id: int,
        stack: AsyncExitStack,
    ) -> CampaignDetailData:
        campaign = await self._campaigns.get_by_id_with_streams(campaign_id)
        if campaign is None:
            raise NotFoundError(
                f"Campaign {campaign_id} was not found.",
                details={"campaign_id": str(campaign_id)},
            )

        keitaro_campaign_id = campaign.keitaro_campaign_id
        existing_has_offers = {s.keitaro_stream_id: s.has_offers for s in campaign.streams}
        dirty_stream_ids = [s.id for s in campaign.streams if s.is_dirty]
        # End the read transaction before issuing HTTP requests to Keitaro.
        await self._session.commit()

        # Block concurrent edits of this campaign's streams (sorted order avoids lock cycles).
        for local_stream_id in sorted(s.id for s in campaign.streams):
            await stack.enter_async_context(stream_locks.acquire(local_stream_id))
        if dirty_stream_ids:
            logger.warning(
                "FETCH overwrites staged local edits (campaign_id=%s, dirty_stream_ids=%s)",
                campaign_id,
                dirty_stream_ids,
            )

        kt_streams, kt_offers = await asyncio.gather(
            self._keitaro.get_campaign_streams(keitaro_campaign_id),
            self._keitaro.search_offers(None),
        )
        offer_name_map = {offer.id: offer.name for offer in kt_offers}

        async with self._session.begin():
            for kt_stream in kt_streams:
                has_offers = (
                    bool(kt_stream.offers)
                    or existing_has_offers.get(kt_stream.id, False)
                    or (kt_stream.stream_schema == "landings")
                )
                stream = await self._streams.upsert_stream(
                    campaign_id=campaign_id,
                    keitaro_stream_id=kt_stream.id,
                    name=kt_stream.name,
                    position=kt_stream.position,
                    has_offers=has_offers,
                    is_dirty=False,
                )

                if not has_offers:
                    continue

                # Aggregate duplicate offer ids returned by Keitaro within a single stream.
                aggregated: dict[int, _KtOfferSnapshot] = {}
                for kt_offer in kt_stream.offers:
                    resolved_name = (
                        offer_name_map.get(kt_offer.offer_id)
                        or kt_offer.offer_name
                        or kt_offer.name
                        or f"Offer #{kt_offer.offer_id}"
                    )
                    snapshot = aggregated.setdefault(
                        kt_offer.offer_id,
                        _KtOfferSnapshot(name=resolved_name),
                    )
                    if snapshot.entries:
                        logger.warning(
                            "Keitaro returned duplicate offer in stream "
                            "(keitaro_stream_id=%s, offer_id=%s); summing shares",
                            kt_stream.id,
                            kt_offer.offer_id,
                        )
                    snapshot.entries += 1
                    if kt_offer.state == "active" and kt_offer.share > 0:
                        snapshot.active_share += kt_offer.share

                for kt_offer_id, snapshot in aggregated.items():
                    is_active = snapshot.active_share > 0
                    share = min(snapshot.active_share, 100)
                    await self._streams.upsert_offer(
                        stream_id=stream.id,
                        keitaro_offer_id=kt_offer_id,
                        offer_name=snapshot.name,
                        share=share if is_active else 0,
                        is_pinned=False,
                        status="active" if is_active else "removed",
                        is_published=True,
                        published_share=share if is_active else 0,
                        published_status="active" if is_active else "removed",
                    )

                local_offers = await self._streams.list_offers_by_stream(stream.id)
                for local_offer in local_offers:
                    if local_offer.keitaro_offer_id in aggregated:
                        continue
                    if not local_offer.is_published:
                        # Unpublished draft that Keitaro never knew: drop it, do not ghost it.
                        await self._session.delete(local_offer)
                        continue
                    local_offer.status = "removed"
                    local_offer.share = 0
                    local_offer.is_pinned = False
                    local_offer.is_published = True
                    local_offer.published_share = 0
                    local_offer.published_status = "removed"

                await self._session.flush()

        refreshed = await self._campaigns.get_by_id_with_streams(campaign_id)
        if refreshed is None:
            raise NotFoundError(
                f"Campaign {campaign_id} was not found.",
                details={"campaign_id": str(campaign_id)},
            )
        await self._session.commit()
        return campaign_to_detail(refreshed)

    async def add_offer(self, stream_id: int, offer_id: int, offer_name: str) -> StreamData:
        """Stage a new (or reactivated) offer in the stream and recalculate shares."""
        async with stream_locks.acquire(stream_id):
            return await self._add_offer(stream_id, offer_id, offer_name)

    async def _add_offer(self, stream_id: int, offer_id: int, offer_name: str) -> StreamData:
        """Stage a new (or reactivated) offer in the stream and recalculate shares."""
        if offer_id <= 0:
            raise DomainValidationError(
                "offer_id must be a positive integer.",
                details={"offer_id": str(offer_id)},
            )

        cleaned_name = offer_name.strip() or f"Offer #{offer_id}"
        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            existing = next(
                (o for o in stream.offers if o.keitaro_offer_id == offer_id),
                None,
            )
            if existing is not None:
                if existing.status == "active":
                    raise ConflictError(
                        f"Offer {offer_id} is already active in stream {stream_id}.",
                        details={"stream_id": str(stream_id), "offer_id": str(offer_id)},
                    )
                existing.status = "active"
                existing.is_pinned = False
                existing.offer_name = cleaned_name
            else:
                new_offer = StreamOffer(
                    stream_id=stream.id,
                    keitaro_offer_id=offer_id,
                    offer_name=cleaned_name,
                    share=0,
                    is_pinned=False,
                    status="active",
                    is_published=False,
                    published_share=None,
                    published_status=None,
                )
                self._session.add(new_offer)
                stream.offers.append(new_offer)

            recalculate_shares(stream.offers)
            stream.is_dirty = True
            try:
                await self._session.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    f"Offer {offer_id} already exists in stream {stream_id}.",
                    details={"stream_id": str(stream_id), "offer_id": str(offer_id)},
                ) from exc

        return await self._reload_stream_data(stream_id)

    async def remove_offer(self, stream_id: int, offer_id: int) -> StreamData:
        """Archive an active offer locally (`removed`) and redistribute remaining shares."""
        async with stream_locks.acquire(stream_id):
            return await self._remove_offer(stream_id, offer_id)

    async def _remove_offer(self, stream_id: int, offer_id: int) -> StreamData:
        """Archive an active offer locally (`removed`) and redistribute remaining shares."""
        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            offer = self._find_offer(stream, offer_id)
            if offer.status == "removed":
                raise DomainValidationError(
                    f"Offer {offer_id} is already removed in stream {stream_id}.",
                    details={"stream_id": str(stream_id), "offer_id": str(offer_id)},
                )

            offer.status = "removed"
            offer.share = 0
            offer.is_pinned = False

            remaining_active = [o for o in stream.offers if o.status == "active"]
            if remaining_active:
                if all(o.is_pinned for o in remaining_active) and (
                    sum(o.share for o in remaining_active) != 100
                ):
                    # Only pinned offers are left and they no longer sum to 100: rebalance.
                    for active_offer in remaining_active:
                        active_offer.is_pinned = False
                recalculate_shares(stream.offers)

            stream.is_dirty = True
            await self._session.flush()

        return await self._reload_stream_data(stream_id)

    async def bring_back_offer(self, stream_id: int, offer_id: int) -> StreamData:
        """Restore a locally archived (`removed`) offer back to `active` and recalculate shares."""
        async with stream_locks.acquire(stream_id):
            return await self._bring_back_offer(stream_id, offer_id)

    async def _bring_back_offer(self, stream_id: int, offer_id: int) -> StreamData:
        """Restore a locally archived (`removed`) offer back to `active` and recalculate shares."""
        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            offer = self._find_offer(stream, offer_id)
            if offer.status != "removed":
                raise DomainValidationError(
                    f"Offer {offer_id} is already active in stream {stream_id}.",
                    details={"stream_id": str(stream_id), "offer_id": str(offer_id)},
                )

            offer.status = "active"
            offer.is_pinned = False
            recalculate_shares(stream.offers)
            stream.is_dirty = True
            await self._session.flush()

        return await self._reload_stream_data(stream_id)

    async def toggle_pin(
        self,
        stream_id: int,
        offer_id: int,
        *,
        share: int | None = None,
    ) -> StreamData:
        """Toggle pin state (or pin to an explicit share 1..100) and recalculate shares."""
        async with stream_locks.acquire(stream_id):
            return await self._toggle_pin(stream_id, offer_id, share=share)

    async def _toggle_pin(
        self,
        stream_id: int,
        offer_id: int,
        *,
        share: int | None = None,
    ) -> StreamData:
        """Toggle pin state (or pin to an explicit share 1..100) and recalculate shares."""
        if share is not None and not (1 <= share <= 100):
            raise DomainValidationError(
                "Pinned share must be an integer between 1 and 100.",
                details={"share": str(share)},
            )

        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            offer = self._find_offer(stream, offer_id)
            if offer.status != "active":
                raise DomainValidationError(
                    "Only active offers can be pinned.",
                    details={"stream_id": str(stream_id), "offer_id": str(offer_id)},
                )

            if share is None:
                offer.is_pinned = not offer.is_pinned
            else:
                offer.is_pinned = True
                offer.share = share

            recalculate_shares(stream.offers)
            stream.is_dirty = True
            await self._session.flush()

        return await self._reload_stream_data(stream_id)

    async def cancel_changes(self, stream_id: int) -> StreamData:
        """Discard staged local edits: delete unpublished rows and restore published snapshots."""
        async with stream_locks.acquire(stream_id):
            return await self._cancel_changes(stream_id)

    async def _cancel_changes(self, stream_id: int) -> StreamData:
        """Discard staged local edits: delete unpublished rows and restore published snapshots."""
        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            for offer in list(stream.offers):
                if not offer.is_published:
                    stream.offers.remove(offer)
                    await self._session.delete(offer)
                else:
                    offer.share = offer.published_share if offer.published_share is not None else 0
                    offer.status = (
                        offer.published_status
                        if offer.published_status in ("active", "removed")
                        else "active"
                    )
                    offer.is_pinned = False

            stream.is_dirty = False
            await self._session.flush()

        return await self._reload_stream_data(stream_id)

    async def rebalance_stream(self, stream_id: int) -> StreamData:
        """Unpin all active offers and evenly redistribute shares to sum to 100%."""
        async with stream_locks.acquire(stream_id):
            return await self._rebalance_stream(stream_id)

    async def _rebalance_stream(self, stream_id: int) -> StreamData:
        """Unpin all active offers and evenly redistribute shares to sum to 100%."""
        async with self._session.begin():
            stream = await self._get_editable_stream(stream_id)
            active = [o for o in stream.offers if o.status == "active"]
            if not active:
                raise DomainValidationError(
                    "Stream must have at least one active offer to rebalance.",
                    details={"stream_id": str(stream_id)},
                )

            # Unpin all active offers so recalculate_shares distributes evenly.
            for offer in active:
                offer.is_pinned = False

            recalculate_shares(stream.offers)
            stream.is_dirty = True
            await self._session.flush()

        return await self._reload_stream_data(stream_id)

    async def push_to_kt(self, stream_id: int) -> StreamData:
        """Validate staged offers, push active offers to Keitaro, and update published state."""
        async with stream_locks.acquire(stream_id):
            return await self._push_to_kt(stream_id)

    async def _push_to_kt(self, stream_id: int) -> StreamData:
        stream = await self._get_editable_stream(stream_id)
        can_push, err = validate_stream_for_push(stream.offers)
        if not can_push:
            raise DomainValidationError(
                err or "Invalid stream state.",
                details={"stream_id": str(stream_id)},
            )

        ordered_active = sorted(
            (o for o in stream.offers if o.status == "active"),
            key=lambda o: o.id,
        )
        payload = [
            KeitaroStreamOfferItem(
                offer_id=offer.keitaro_offer_id,
                share=offer.share,
                state="active",
            )
            for offer in ordered_active
        ]
        # Immutable record of exactly what is sent; local state may change during the HTTP call.
        pushed_snapshot: dict[int, int] = {o.keitaro_offer_id: o.share for o in ordered_active}
        keitaro_stream_id = stream.keitaro_stream_id
        # End the read transaction before calling Keitaro over HTTP.
        await self._session.commit()

        await self._keitaro.update_stream_offers(keitaro_stream_id, payload)

        # Keitaro is updated: finish local sync even if the client disconnects now.
        await run_shielded(
            self._apply_push_result(stream_id, keitaro_stream_id, pushed_snapshot),
            name=f"push_sync:{stream_id}",
        )
        return await self._reload_stream_data(stream_id)

    async def _apply_push_result(
        self,
        stream_id: int,
        keitaro_stream_id: int,
        pushed_snapshot: dict[int, int],
    ) -> None:
        """Record published state strictly from the pushed snapshot using a dedicated session."""
        try:
            async with self._session_factory() as session:
                streams = StreamRepository(session)
                async with session.begin():
                    stream = await streams.get_stream_by_id(stream_id)
                    if stream is None:
                        raise NotFoundError(
                            f"Stream {stream_id} was not found.",
                            details={"stream_id": str(stream_id)},
                        )
                    for offer in list(stream.offers):
                        if offer.keitaro_offer_id in pushed_snapshot:
                            offer.is_published = True
                            offer.published_share = pushed_snapshot[offer.keitaro_offer_id]
                            offer.published_status = "active"
                        elif offer.status == "removed" and not offer.is_published:
                            stream.offers.remove(offer)
                            await session.delete(offer)
                        elif offer.is_published or offer.status == "removed":
                            # Not part of the push: Keitaro no longer lists it.
                            offer.is_published = True
                            offer.published_share = 0
                            offer.published_status = "removed"
                            if offer.status == "removed":
                                offer.share = 0
                                offer.is_pinned = False
                        # else: active draft staged after the snapshot -> leave untouched.

                    current_active = {
                        o.keitaro_offer_id: o.share for o in stream.offers if o.status == "active"
                    }
                    # Stay dirty if edits landed while the PUT was in flight.
                    stream.is_dirty = current_active != pushed_snapshot
                    await session.flush()
        except BaseException:
            logger.critical(
                "Local DB persistence failed after pushing stream offers to Keitaro "
                "(stream_id=%s, keitaro_stream_id=%s)",
                stream_id,
                keitaro_stream_id,
            )
            raise
