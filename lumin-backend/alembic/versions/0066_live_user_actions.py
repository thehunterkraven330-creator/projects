"""live: the host can mute or block a person in their live

Revision ID: 0066_live_user_actions
Revises: 0065_live_thumbnail_report
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0066_live_user_actions"
down_revision = "0065_live_thumbnail_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "live_user_actions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "live_user_actions",
        sa.Column("stream_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("live_streams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("live_user_actions")
