"""live shopping: streams, the products shown in them, chat and who is watching

Revision ID: 0063_live_streams
Revises: 0062_more_categories_actor_backfill
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0063_live_streams"
down_revision = "0062_more_categories_actor_backfill"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    if not _has_table("live_streams"):
        op.create_table(
            "live_streams",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("host_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("room_name", sa.String(80), nullable=False, unique=True),
            sa.Column("status", sa.String(10), nullable=False, server_default="live"),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("peak_viewers", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_live_streams_host_id", "live_streams", ["host_id"])
        op.create_index("ix_live_streams_status", "live_streams", ["status"])
    if not _has_table("live_stream_products"):
        op.create_table(
            "live_stream_products",
            sa.Column("stream_id", uuid, sa.ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        )
    if not _has_table("live_messages"):
        op.create_table(
            "live_messages",
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("stream_id", uuid, sa.ForeignKey("live_streams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("body", sa.String(300), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_live_messages_stream_id", "live_messages", ["stream_id"])
    if not _has_table("live_viewers"):
        op.create_table(
            "live_viewers",
            sa.Column("stream_id", uuid, sa.ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for t in ("live_viewers", "live_messages", "live_stream_products", "live_streams"):
        op.drop_table(t)
