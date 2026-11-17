"""Shared FastAPI dependency providers and annotated type aliases."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.core.config import Settings, get_settings
from adrobot.core.exceptions import ConfigurationError
from adrobot.db.session import get_db_session, get_session_factory
from adrobot.integrations.keitaro import KeitaroClient
from adrobot.services import CampaignService, StreamEditorService

AppSettings = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


def get_keitaro_client(request: Request) -> KeitaroClient:
    """Return the shared KeitaroClient created in the application lifespan (never closed here)."""
    client: KeitaroClient | None = getattr(request.app.state, "keitaro_client", None)
    if client is None:
        raise ConfigurationError(
            "Keitaro client is not configured; check KEITARO_API_URL and KEITARO_API_KEY.",
            details={"field": "keitaro_api_url"},
        )
    return client


KeitaroClientDep = Annotated[KeitaroClient, Depends(get_keitaro_client)]


def get_campaign_service(
    session: DbSession,
    session_factory: SessionFactory,
    keitaro: KeitaroClientDep,
    settings: AppSettings,
) -> CampaignService:
    """Construct CampaignService for the current request scope."""
    return CampaignService(
        session=session,
        session_factory=session_factory,
        keitaro=keitaro,
        settings=settings,
    )


def get_stream_editor_service(
    session: DbSession,
    session_factory: SessionFactory,
    keitaro: KeitaroClientDep,
) -> StreamEditorService:
    """Construct StreamEditorService for the current request scope."""
    return StreamEditorService(
        session=session,
        session_factory=session_factory,
        keitaro=keitaro,
    )


CampaignServiceDep = Annotated[CampaignService, Depends(get_campaign_service)]
StreamEditorServiceDep = Annotated[StreamEditorService, Depends(get_stream_editor_service)]
