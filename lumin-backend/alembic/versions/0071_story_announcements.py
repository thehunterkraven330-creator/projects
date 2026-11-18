"""story announcements: kind (post/live/sale) and the time it counts down to

Revision ID: 0071_story_announcements
Revises: 0070_scans_count
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0071_story_announcements"
down_revision = "0070_scans_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("kind", sa.String(8), nullable=False, server_default="post"))
    op.add_column("stories", sa.Column("event_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "event_at")
    op.drop_column("stories", "kind")
