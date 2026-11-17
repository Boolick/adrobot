"""Async SQLAlchemy 2.0 engine, DeclarativeBase, and session lifecycle."""

from collections.abc import AsyncIterator
from typing import ClassVar, Protocol

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from adrobot.core.config import get_settings


class _DBAPICursor(Protocol):
    def execute(self, statement: str, /) -> object: ...
    def close(self) -> object: ...


class _DBAPIConnection(Protocol):
    def cursor(self) -> _DBAPICursor: ...


NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    metadata: ClassVar[MetaData] = MetaData(naming_convention=NAMING_CONVENTION)


def _enable_sqlite_foreign_keys(
    dbapi_connection: _DBAPIConnection,
    _connection_record: object,
) -> None:
    """Enable SQLite foreign key constraint checks and ON DELETE CASCADE per connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_engine_from_url(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create a configured async SQLAlchemy engine for the given database URL."""
    connect_args: dict[str, object] = {}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # Required by SQLite driver when connections cross asyncio worker threads.
        connect_args["check_same_thread"] = False

    async_engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if is_sqlite:
        event.listen(async_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return async_engine


_settings = get_settings()
engine: AsyncEngine = create_engine_from_url(
    _settings.database_url,
    echo=_settings.db_echo,
)
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session and roll back on unhandled errors."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
