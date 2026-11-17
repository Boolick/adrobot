"""Shared FastAPI dependency providers and annotated type aliases."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adrobot.core.config import Settings, get_settings
from adrobot.db.session import get_db_session
from adrobot.integrations.keitaro import KeitaroClient
from adrobot.services import CampaignService, StreamEditorService

AppSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_keitaro_client(settings: AppSettings) -> AsyncIterator[KeitaroClient]:
    """Yield a managed KeitaroClient configured from runtime application settings."""
    async with KeitaroClient(
        base_url=settings.keitaro_api_url,
        api_key=settings.keitaro_api_key,
        timeout_seconds=settings.keitaro_timeout_seconds,
    ) as client:
        yield client


KeitaroClientDep = Annotated[KeitaroClient, Depends(get_keitaro_client)]


def get_campaign_service(
    session: DbSession,
    keitaro: KeitaroClientDep,
    settings: AppSettings,
) -> CampaignService:
    """Construct CampaignService for the current request scope."""
    return CampaignService(session=session, keitaro=keitaro, settings=settings)


def get_stream_editor_service(
    session: DbSession,
    keitaro: KeitaroClientDep,
) -> StreamEditorService:
    """Construct StreamEditorService for the current request scope."""
    return StreamEditorService(session=session, keitaro=keitaro)


CampaignServiceDep = Annotated[CampaignService, Depends(get_campaign_service)]
StreamEditorServiceDep = Annotated[StreamEditorService, Depends(get_stream_editor_service)]
