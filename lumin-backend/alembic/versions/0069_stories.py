"""stories: 24-hour pictures and clips, who has seen them, and stories can be reported

Revision ID: 0069_stories
Revises: 0068_product_visuals
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0069_stories"
down_revision = "0068_product_visuals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_url", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(10), nullable=False),
        sa.Column("caption", sa.String(200), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("audience", sa.String(12), nullable=False, server_default="everyone"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moderation_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stories_author_id", "stories", ["author_id"])
    op.create_index("ix_stories_expires_at", "stories", ["expires_at"])
    op.create_index("ix_stories_author_expires", "stories", ["author_id", "expires_at"])
    op.create_table(
        "story_views",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("viewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reaction", sa.String(8), nullable=True),
    )
    op.create_index("ix_story_views_viewer_id", "story_views", ["viewer_id"])
    # ALTER TYPE ... ADD VALUE cannot run inside the migration transaction; skipped if the type was never created.
    exists = op.get_bind().execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'report_target_type'")).first()
    if exists:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE report_target_type ADD VALUE IF NOT EXISTS 'story'")


def downgrade() -> None:
    op.drop_index("ix_story_views_viewer_id", table_name="story_views")
    op.drop_table("story_views")
    op.drop_index("ix_stories_author_expires", table_name="stories")
    op.drop_index("ix_stories_expires_at", table_name="stories")
    op.drop_index("ix_stories_author_id", table_name="stories")
    op.drop_table("stories")
