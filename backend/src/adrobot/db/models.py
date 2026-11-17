"""SQLAlchemy 2.0 ORM models for Adrobot local persistence."""

from datetime import datetime
from typing import Literal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adrobot.db.session import Base

OfferStatus = Literal["active", "removed"]


class Campaign(Base):
    """Local tracking record for a campaign created or managed in Keitaro."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geo: Mapped[str] = mapped_column(String(100), nullable=False)
    domain_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    streams: Mapped[list["CampaignStream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignStream.position, CampaignStream.id",
        lazy="raise_on_sql",
    )

    def __repr__(self) -> str:
        return (
            f"Campaign(id={self.id!r}, "
            f"keitaro_campaign_id={self.keitaro_campaign_id!r}, "
            f"name={self.name!r})"
        )


class CampaignStream(Base):
    """Local staging record for a Keitaro campaign stream."""

    __tablename__ = "campaign_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    keitaro_stream_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    has_offers: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    is_dirty: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    campaign: Mapped["Campaign"] = relationship(
        back_populates="streams",
        lazy="raise_on_sql",
    )
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.id",
        lazy="raise_on_sql",
    )

    def __repr__(self) -> str:
        return (
            f"CampaignStream(id={self.id!r}, "
            f"campaign_id={self.campaign_id!r}, "
            f"keitaro_stream_id={self.keitaro_stream_id!r}, "
            f"name={self.name!r})"
        )


class StreamOffer(Base):
    """Local staging record for an offer assigned to a campaign stream."""

    __tablename__ = "stream_offers"
    __table_args__ = (
        UniqueConstraint(
            "stream_id",
            "keitaro_offer_id",
            name="uq_stream_offers_stream_id_keitaro_offer_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaign_streams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    keitaro_offer_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
    )
    offer_name: Mapped[str] = mapped_column(
        String(255),
        default="",
        server_default=text("''"),
        nullable=False,
    )
    share: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default=text("'active'"),
        nullable=False,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )
    published_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    stream: Mapped["CampaignStream"] = relationship(
        back_populates="offers",
        lazy="raise_on_sql",
    )

    def __repr__(self) -> str:
        return (
            f"StreamOffer(id={self.id!r}, "
            f"stream_id={self.stream_id!r}, "
            f"keitaro_offer_id={self.keitaro_offer_id!r}, "
            f"status={self.status!r}, "
            f"share={self.share!r})"
        )
