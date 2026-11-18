"""notifications: fill in the person for old follow and birthday notices

Revision ID: 0061_notification_actor_backfill
Revises: 0060_notification_actor
Create Date: 2026-11-13
"""
from alembic import op

revision = "0061_notification_actor_backfill"
down_revision = "0060_notification_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A follow or birthday notice already stored the person it is about (target_id), so their picture can show on the old ones.
    # Likes and comments never recorded who did them, so those older notices keep the type icon only; new ones carry the person.
    op.execute(
        "UPDATE notifications SET actor_id = target_id WHERE actor_id IS NULL AND type IN ('follow', 'birthday') "
        "AND target_id IN (SELECT id FROM users)"
    )


def downgrade() -> None:
    pass
