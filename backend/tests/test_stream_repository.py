"""Async integration tests for CampaignStream, StreamOffer, and StreamRepository."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.core.exceptions import ResourceConflictError, ResourceNotFoundError
from adrobot.db.models import Campaign, CampaignStream
from adrobot.db.repositories.campaigns import CampaignRepository
from adrobot.db.repositories.streams import StreamRepository
from adrobot.db.session import Base, create_engine_from_url


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provision an isolated in-memory async SQLite database per test."""
    engine = create_engine_from_url("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        yield factory
    finally:
        await engine.dispose()


async def _create_sample_campaign(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    keitaro_campaign_id: int = 1001,
    name: str = "test_bullo_campaign1",
) -> Campaign:
    async with session_factory() as session:
        repo = CampaignRepository(session)
        async with session.begin():
            return await repo.create(
                keitaro_campaign_id=keitaro_campaign_id,
                name=name,
                alias="test-bullo-campaign1",
                geo="AU",
                domain_id=1813,
                group_id=10332,
                source_id=836,
            )


async def test_create_stream_populates_defaults_and_eager_offers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify create_stream() sets defaults/timestamps and loads offers without lazy queries."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            flow1 = await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=501,
                name="Geo -> Google",
            )
            assert flow1.id > 0
            assert flow1.position == 1
            assert flow1.has_offers is False
            assert flow1.is_dirty is False
            assert flow1.created_at is not None
            assert flow1.updated_at is not None
            assert flow1.offers == []

    # Accessing offers outside session verifies zero lazy loads.
    assert flow1.offers == []


async def test_create_stream_respects_outer_transaction_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify flush() inside create_stream() rolls back on outer exception."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        with pytest.raises(RuntimeError, match="abort"):
            async with session.begin():
                await repo.create_stream(
                    campaign_id=campaign.id,
                    keitaro_stream_id=502,
                    name="Offers",
                    position=2,
                    has_offers=True,
                )
                raise RuntimeError("abort")

    async with session_factory() as verify_session:
        assert await StreamRepository(verify_session).get_stream_by_keitaro_id(502) is None


async def test_create_stream_conflict_and_missing_campaign_errors(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify duplicate keitaro_stream_id and unknown campaign_id raise domain exceptions."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=601,
                name="Offers",
                position=2,
                has_offers=True,
            )

    async with session_factory() as dup_session:
        repo = StreamRepository(dup_session)
        with pytest.raises(ResourceConflictError) as conflict_exc:
            async with dup_session.begin():
                await repo.create_stream(
                    campaign_id=campaign.id,
                    keitaro_stream_id=601,
                    name="Duplicate",
                )
        assert conflict_exc.value.status_code == 409
        assert conflict_exc.value.details == {"keitaro_stream_id": "601"}

    async with session_factory() as fk_session:
        repo = StreamRepository(fk_session)
        with pytest.raises(ResourceNotFoundError) as not_found_exc:
            async with fk_session.begin():
                await repo.create_stream(
                    campaign_id=999999,
                    keitaro_stream_id=602,
                    name="Orphan",
                )
        assert not_found_exc.value.status_code == 404
        assert not_found_exc.value.details == {"campaign_id": "999999"}


async def test_list_streams_and_selectinload_prevents_lazy_loads(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify list_streams_by_campaign orders by position and eagerly loads offers."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            s2 = await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=702,
                name="Offers",
                position=2,
                has_offers=True,
            )
            await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=701,
                name="Geo -> Google",
                position=1,
                has_offers=False,
            )
            await repo.create_offer(
                stream_id=s2.id,
                keitaro_offer_id=55,
                offer_name="Offer 55",
                share=100,
                published_share=100,
                published_status="active",
            )

    async with session_factory() as read_session:
        streams = await StreamRepository(read_session).list_streams_by_campaign(campaign.id)

    async with session_factory() as bare_session:
        # Verify bare select without selectinload raises if relationship is touched.
        bare_stream = await bare_session.scalar(
            select(CampaignStream).where(CampaignStream.keitaro_stream_id == 702)
        )
        assert bare_stream is not None
        with pytest.raises(InvalidRequestError):
            _ = bare_stream.offers

    # Outside session: eagerly loaded collections remain accessible.
    assert [s.keitaro_stream_id for s in streams] == [701, 702]
    assert streams[0].has_offers is False
    assert streams[0].offers == []
    assert streams[1].has_offers is True
    assert len(streams[1].offers) == 1
    assert streams[1].offers[0].keitaro_offer_id == 55
    assert streams[1].offers[0].share == 100


async def test_upsert_stream_and_set_dirty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify upsert_stream creates/updates cleanly and set_stream_dirty validates existence."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            created = await repo.upsert_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=801,
                name="Offers",
                position=2,
                has_offers=True,
            )
            await repo.set_stream_dirty(created.id, is_dirty=True)
            updated = await repo.upsert_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=801,
                name="Offers Renamed",
                position=3,
                has_offers=True,
            )
            assert updated.id == created.id
            assert updated.name == "Offers Renamed"
            assert updated.position == 3
            assert updated.is_dirty is True

            with pytest.raises(ResourceNotFoundError):
                await repo.set_stream_dirty(999999, is_dirty=False)


async def test_stream_offer_staging_crud_uniqueness_and_unpublished_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify StreamOffer defaults, unique constraint, upsert, and unpublished deletion."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            stream = await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=901,
                name="Offers",
                position=2,
                has_offers=True,
            )
            published_offer = await repo.create_offer(
                stream_id=stream.id,
                keitaro_offer_id=10,
                offer_name="Published Offer",
                share=50,
                is_pinned=True,
                status="active",
                is_published=True,
                published_share=100,
                published_status="active",
            )
            draft_offer = await repo.create_offer(
                stream_id=stream.id,
                keitaro_offer_id=20,
                offer_name="Draft Offer",
                share=50,
                is_published=False,
            )
            removed_offer = await repo.create_offer(
                stream_id=stream.id,
                keitaro_offer_id=30,
                status="removed",
                is_published=True,
                published_share=0,
                published_status="removed",
            )
            assert published_offer.is_pinned is True
            assert draft_offer.is_published is False
            assert removed_offer.offer_name == ""
            assert removed_offer.share == 0

    async with session_factory() as dup_session:
        repo = StreamRepository(dup_session)
        with pytest.raises(ResourceConflictError) as conflict_exc:
            async with dup_session.begin():
                await repo.create_offer(stream_id=stream.id, keitaro_offer_id=10)
        assert conflict_exc.value.details == {
            "stream_id": str(stream.id),
            "keitaro_offer_id": "10",
        }

    async with session_factory() as edit_session:
        repo = StreamRepository(edit_session)
        async with edit_session.begin():
            active_offers = await repo.list_offers_by_stream(stream.id, status="active")
            assert [o.keitaro_offer_id for o in active_offers] == [10, 20]

            upserted = await repo.upsert_offer(
                stream_id=stream.id,
                keitaro_offer_id=10,
                offer_name="Published Offer Updated",
                share=100,
                is_pinned=False,
                status="active",
                is_published=True,
                published_share=100,
                published_status="active",
            )
            assert upserted.id == published_offer.id
            assert upserted.offer_name == "Published Offer Updated"

            deleted_count = await repo.delete_unpublished_offers(stream.id)
            assert deleted_count == 1

            deleted_single = await repo.delete_offer(stream.id, 30)
            assert deleted_single is True
            assert await repo.delete_offer(stream.id, 9999) is False

    async with session_factory() as verify_session:
        remaining = await StreamRepository(verify_session).list_offers_by_stream(stream.id)
        assert [o.keitaro_offer_id for o in remaining] == [10]


async def test_cascade_delete_from_campaign_and_eager_campaign_loading(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify CampaignRepository eager stream loading and SQLite ON DELETE CASCADE."""
    campaign = await _create_sample_campaign(session_factory)

    async with session_factory() as session:
        repo = StreamRepository(session)
        async with session.begin():
            stream = await repo.create_stream(
                campaign_id=campaign.id,
                keitaro_stream_id=950,
                name="Offers",
                position=2,
                has_offers=True,
            )
            await repo.create_offer(
                stream_id=stream.id,
                keitaro_offer_id=77,
                offer_name="Offer 77",
                share=100,
            )

    async with session_factory() as read_session:
        loaded = await CampaignRepository(read_session).get_by_keitaro_id_with_streams(
            campaign.keitaro_campaign_id
        )
        assert loaded is not None

    # Accessible after session close (zero lazy loads).
    assert len(loaded.streams) == 1
    assert len(loaded.streams[0].offers) == 1
    assert loaded.streams[0].offers[0].keitaro_offer_id == 77

    # SQL-level DELETE must cascade via PRAGMA foreign_keys=ON.
    async with session_factory() as delete_session, delete_session.begin():
        await delete_session.execute(delete(Campaign).where(Campaign.id == campaign.id))

    async with session_factory() as verify_session:
        assert await StreamRepository(verify_session).get_stream_by_id(stream.id) is None
        assert await StreamRepository(verify_session).get_offer(stream.id, 77) is None
