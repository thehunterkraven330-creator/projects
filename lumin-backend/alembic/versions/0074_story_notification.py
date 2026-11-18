"""notification type for story announcements (a followed seller announced a live or a flash sale)

Revision ID: 0074_story_notification
Revises: 0073_story_columns_repair
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0074_story_notification"
down_revision = "0073_story_columns_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    exists = op.get_bind().execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'notification_type'")).first()
    if exists:
        # ALTER TYPE ... ADD VALUE cannot run inside the migration transaction.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'story'")


def downgrade() -> None:
    pass
