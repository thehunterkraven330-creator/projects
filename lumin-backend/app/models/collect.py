"""A buyer's claim that they travelled to collect an item and nobody was there. One row per claim (a claim covers every unit
bought together). The buyer is refunded straight away; the seller's strike is only counted when an admin confirms the claim."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk

NOSHOW_CLAIMED = "claimed"  # waiting for the seller's reply or an admin
NOSHOW_DISPUTED = "disputed"  # the seller replied that they were there
NOSHOW_CONFIRMED = "confirmed"  # an admin agreed: the seller got a strike
NOSHOW_DISMISSED = "dismissed"  # an admin did not: no strike


class CollectNoShow(Base, TimestampMixin):
    __tablename__ = "collect_no_shows"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchant_accounts.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=NOSHOW_CLAIMED, index=True)
    # "not_there": nobody was at the pickup address. "refused": the seller was there but would not show or sell the item.
    kind: Mapped[str] = mapped_column(String(16), default="not_there", server_default="not_there")
    # What the buyer said they planned (their "I'm coming on ..."), their photo of the place, and what they wrote.
    planned_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    photo_url: Mapped[str] = mapped_column(String(600))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The seller's answer.
    seller_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_photo_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    seller_replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
