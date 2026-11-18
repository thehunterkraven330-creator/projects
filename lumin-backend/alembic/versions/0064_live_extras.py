"""live: hearts, recordings, and the "went live" notification type

Revision ID: 0064_live_extras
Revises: 0063_live_streams
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0064_live_extras"
down_revision = "0063_live_streams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("live_streams")}
    if "heart_count" not in cols:
        op.add_column("live_streams", sa.Column("heart_count", sa.Integer, nullable=False, server_default="0"))
    if "egress_id" not in cols:
        op.add_column("live_streams", sa.Column("egress_id", sa.String(80), nullable=True))
    if "replay_url" not in cols:
        op.add_column("live_streams", sa.Column("replay_url", sa.String(500), nullable=True))
    # ALTER TYPE ... ADD VALUE cannot run inside the migration transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'live'")


def downgrade() -> None:
    pass
