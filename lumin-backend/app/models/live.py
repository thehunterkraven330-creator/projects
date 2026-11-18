import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, uuid_pk

# The products a host is showing in a live stream (tapped from the watch screen to open the product).
live_stream_products = Table(
    "live_stream_products",
    Base.metadata,
    Column("stream_id", UUID(as_uuid=True), ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True),
    Column("product_id", UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
)


class LiveStream(Base, TimestampMixin):
    """One live broadcast by a merchant. The video itself runs through LiveKit (room_name is its room); this row is what the app lists,
    shows the title/host/products from, and uses to know when it ends. A stream whose host stopped sending heartbeats (closed the tab,
    lost signal) is treated as ended — see routers/live.py."""

    __tablename__ = "live_streams"

    id: Mapped[uuid.UUID] = uuid_pk()
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    room_name: Mapped[str] = mapped_column(String(80), unique=True)
    # "live" or "ended" (a plain string, not a database enum, so it never needs a migration to change)
    status: Mapped[str] = mapped_column(String(10), default="live", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bumped by the host's browser every ~20s while broadcasting.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    peak_viewers: Mapped[int] = mapped_column(Integer, default=0)
    # Hearts sent by viewers, all together. Everyone's poll reads this total; a bigger number than last time = hearts to float.
    heart_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The recording (LiveKit egress writes an mp4 to our storage). egress_id is set when recording started; replay_url when the live
    # ended after being recorded. The file finishes a few seconds after the end, so the replay can take a moment to play.
    egress_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    replay_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # A frame of the live itself, taken by the host's browser while broadcasting. Shown on the live tile and, after the live ends,
    # on the Recent lives tile.
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    host = relationship("User", foreign_keys=[host_id], lazy="joined")
    products = relationship("Product", secondary=live_stream_products, lazy="selectin")


class LiveMessage(Base):
    """A chat line in a live stream. Integer ids so viewers can ask for "everything after the last one I have"."""

    __tablename__ = "live_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("live_streams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="joined")


class LiveViewer(Base):
    """Who is watching right now: each viewer's screen refreshes last_seen_at while it is open; "watching" = seen in the last 30s."""

    __tablename__ = "live_viewers"

    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiveUserAction(Base):
    """What the host did about a person in ONE live: "mute" (their chat lines are hidden and they cannot write) or "block" (also
    removed from the live and not allowed back in). Lasts for that live only."""

    __tablename__ = "live_user_actions"

    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # 'mute' | 'block'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
