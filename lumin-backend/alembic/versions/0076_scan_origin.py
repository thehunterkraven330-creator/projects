"""who is behind a scan (device id, hashed network address) so signed-out searches can be counted once per device

Revision ID: 0076_scan_origin
Revises: 0075_scan_count_unique
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0076_scan_origin"
down_revision = "0075_scan_count_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_scans", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("video_scans", sa.Column("ip_hash", sa.String(64), nullable=True))
    op.add_column("video_scans", sa.Column("counted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_video_scans_device", "video_scans", ["video_post_id", "device_id"])
    op.create_index("ix_video_scans_ip_counted", "video_scans", ["ip_hash", "created_at"], postgresql_where=sa.text("counted"))


def downgrade() -> None:
    op.drop_index("ix_video_scans_ip_counted", table_name="video_scans")
    op.drop_index("ix_video_scans_device", table_name="video_scans")
    op.drop_column("video_scans", "counted")
    op.drop_column("video_scans", "ip_hash")
    op.drop_column("video_scans", "device_id")
