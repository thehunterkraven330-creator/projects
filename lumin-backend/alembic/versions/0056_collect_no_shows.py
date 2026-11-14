"""collect in person: a buyer's "nobody was there" claim, with evidence, awaiting an admin

Revision ID: 0056_collect_no_shows
Revises: 0055_collect_no_show_strikes
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0056_collect_no_shows"
down_revision = "0055_collect_no_show_strikes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "collect_no_shows" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "collect_no_shows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchant_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("planned_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("photo_url", sa.String(600), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("seller_note", sa.Text(), nullable=True),
        sa.Column("seller_photo_url", sa.String(600), nullable=True),
        sa.Column("seller_replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_collect_no_shows_order_id", "collect_no_shows", ["order_id"], unique=True)
    op.create_index("ix_collect_no_shows_merchant_id", "collect_no_shows", ["merchant_id"])
    op.create_index("ix_collect_no_shows_status", "collect_no_shows", ["status"])


def downgrade() -> None:
    if "collect_no_shows" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("collect_no_shows")
