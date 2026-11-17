"""Async integration tests for Campaign ORM model and CampaignRepository."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.core.exceptions import ResourceConflictError
from adrobot.db.repositories.campaigns import CampaignRepository
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


async def test_create_campaign_populates_generated_fields_on_flush(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify create() flushes to populate id and timestamps before commit."""
    async with session_factory() as session:
        repo = CampaignRepository(session)
        async with session.begin():
            campaign = await repo.create(
                keitaro_campaign_id=101,
                name="AU Search",
                alias="au-search",
                geo="AU",
                domain_id=1,
                group_id=2,
                source_id=3,
            )
            assert campaign.id > 0
            assert campaign.created_at is not None
            assert campaign.updated_at is not None
            assert campaign.keitaro_campaign_id == 101
            assert campaign.name == "AU Search"
            assert campaign.alias == "au-search"
            assert campaign.geo == "AU"
            assert campaign.domain_id == 1
            assert campaign.group_id == 2
            assert campaign.source_id == 3

    async with session_factory() as verify_session:
        fetched = await CampaignRepository(verify_session).get_by_keitaro_id(101)
        assert fetched is not None
        assert fetched.id == campaign.id
        assert fetched.name == "AU Search"


async def test_create_does_not_commit_outer_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify flush() inside create() respects outer transaction rollback."""
    async with session_factory() as session:
        repo = CampaignRepository(session)
        with pytest.raises(RuntimeError, match="abort"):
            async with session.begin():
                await repo.create(
                    keitaro_campaign_id=150,
                    name="Rolled Back",
                    geo="MX",
                )
                raise RuntimeError("abort")

    async with session_factory() as verify_session:
        assert await CampaignRepository(verify_session).get_by_keitaro_id(150) is None


async def test_get_by_keitaro_id_returns_record_or_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify lookup by keitaro_campaign_id returns matching row or None."""
    async with session_factory() as session:
        repo = CampaignRepository(session)
        async with session.begin():
            await repo.create(
                keitaro_campaign_id=202,
                name="Multi Geo",
                geo="MX,AU,RO",
            )

    async with session_factory() as read_session:
        repo = CampaignRepository(read_session)
        found = await repo.get_by_keitaro_id(202)
        assert found is not None
        assert found.keitaro_campaign_id == 202
        assert found.alias is None
        assert found.domain_id is None
        assert found.group_id is None
        assert found.source_id is None
        assert await repo.get_by_keitaro_id(999999) is None


async def test_list_all_returns_campaigns_ordered_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify list_all() returns empty list initially and newest-first after inserts."""
    async with session_factory() as empty_session:
        assert await CampaignRepository(empty_session).list_all() == []

    async with session_factory() as write_session:
        repo = CampaignRepository(write_session)
        async with write_session.begin():
            for cid, label in [(301, "First"), (302, "Second"), (303, "Third")]:
                await repo.create(keitaro_campaign_id=cid, name=label, geo="AU")

    async with session_factory() as read_session:
        campaigns = await CampaignRepository(read_session).list_all()
        assert [c.keitaro_campaign_id for c in campaigns] == [303, 302, 301]


async def test_create_duplicate_keitaro_campaign_id_raises_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify duplicate keitaro_campaign_id raises ResourceConflictError."""
    async with session_factory() as session:
        repo = CampaignRepository(session)
        async with session.begin():
            await repo.create(keitaro_campaign_id=404, name="Original", geo="RO")

    async with session_factory() as conflict_session:
        repo = CampaignRepository(conflict_session)
        with pytest.raises(ResourceConflictError) as exc_info:
            async with conflict_session.begin():
                await repo.create(keitaro_campaign_id=404, name="Duplicate", geo="AU")

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "RESOURCE_CONFLICT"
        assert exc_info.value.details == {"keitaro_campaign_id": "404"}

    async with session_factory() as verify_session:
        campaigns = await CampaignRepository(verify_session).list_all()
        assert len(campaigns) == 1
        assert campaigns[0].name == "Original"
