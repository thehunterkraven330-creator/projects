"""live: thumbnail from the video, and live streams can be reported

Revision ID: 0065_live_thumbnail_report
Revises: 0064_live_extras
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0065_live_thumbnail_report"
down_revision = "0064_live_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("live_streams")}
    if "thumbnail_url" not in cols:
        op.add_column("live_streams", sa.Column("thumbnail_url", sa.String(500), nullable=True))
    # ALTER TYPE ... ADD VALUE cannot run inside the migration transaction; skipped if the type was never created.
    exists = op.get_bind().execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'report_target_type'")).first()
    if exists:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE report_target_type ADD VALUE IF NOT EXISTS 'live_stream'")


def downgrade() -> None:
    pass
