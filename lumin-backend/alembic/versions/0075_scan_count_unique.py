"""the public Lumin search count counts each signed-in person once per video

Revision ID: 0075_scan_count_unique
Revises: 0074_story_notification
Create Date: 2026-11-18

Counts made before this change added one for every scan, including repeats from one phone and the poster's own. Recompute them:
distinct signed-in people who found the video, not counting the poster.
"""
import sqlalchemy as sa
from alembic import op

revision = "0075_scan_count_unique"
down_revision = "0074_story_notification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE video_posts vp
            SET scans_count = COALESCE((
                SELECT COUNT(DISTINCT s.user_id)
                FROM video_scans s
                WHERE s.video_post_id = vp.id
                  AND s.found IS TRUE
                  AND s.user_id IS NOT NULL
                  AND s.user_id <> vp.poster_id
            ), 0)
            """
        )
    )


def downgrade() -> None:
    pass
