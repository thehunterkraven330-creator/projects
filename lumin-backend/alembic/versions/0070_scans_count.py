"""video_posts.scans_count: the "Lumin search count" (how many times a video was scanned and found)

Revision ID: 0070_scans_count
Revises: 0069_stories
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0070_scans_count"
down_revision = "0069_stories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_posts", sa.Column("scans_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE video_posts SET scans_count = s.n FROM "
        "(SELECT video_post_id, count(*) AS n FROM video_scans WHERE found AND video_post_id IS NOT NULL GROUP BY video_post_id) s "
        "WHERE video_posts.id = s.video_post_id"
    )


def downgrade() -> None:
    op.drop_column("video_posts", "scans_count")
