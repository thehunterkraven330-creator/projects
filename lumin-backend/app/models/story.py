import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class Story(Base, TimestampMixin):
    """A picture or short clip that disappears after 24 hours (app/routers/stories.py). Anyone can post one, optionally with a
    product tagged. Expired stories are hidden by every query (expires_at) and removed, with their file, by app/stories.py."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = uuid_pk()
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_url: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(10))  # "image" or "video"
    caption: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    audience: Mapped[str] = mapped_column(String(12), default="everyone")  # "everyone" or "followers"
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # A seller's announcement: "post" (the default), "live" (event_at = when they go live) or "sale" (event_at = when the sale ends;
    # product_id is the discounted product). The countdown is shown from event_at; the price itself is the product's own.
    kind: Mapped[str] = mapped_column(String(8), default="post", server_default="post")
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Enough reports hide it for review (the same idea as a held video, see app/stories.py).
    moderation_hold: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (Index("ix_stories_author_expires", "author_id", "expires_at"),)


class StoryView(Base):
    """`viewer` has seen `story`. One row per person; the author can list them."""

    __tablename__ = "story_views"

    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True)
    viewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # One emoji reaction per viewer (see stories.REACTIONS), None when they only watched.
    reaction: Mapped[str | None] = mapped_column(String(8), nullable=True)

    __table_args__ = (Index("ix_story_views_viewer_id", "viewer_id"),)
