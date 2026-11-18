"""repair: add any story columns an earlier copy of 0069_stories did not create (reactions, moderation hold, audience)

An early version of 0069 was applied to some databases before reactions and reporting were added to it, so Alembic thinks
0069 is done but story_views.reaction (and possibly others) is missing. This adds whatever is missing and does nothing
on a database that already has everything.

Revision ID: 0073_story_columns_repair
Revises: 0072_discount_ends_at
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0073_story_columns_repair"
down_revision = "0072_discount_ends_at"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def upgrade() -> None:
    views = _columns("story_views")
    if views and "reaction" not in views:
        op.add_column("story_views", sa.Column("reaction", sa.String(8), nullable=True))
    stories = _columns("stories")
    if stories and "moderation_hold" not in stories:
        op.add_column("stories", sa.Column("moderation_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    if stories and "audience" not in stories:
        op.add_column("stories", sa.Column("audience", sa.String(12), nullable=False, server_default="everyone"))
    if stories and "caption" not in stories:
        op.add_column("stories", sa.Column("caption", sa.String(200), nullable=True))
    if stories and "product_id" not in stories:
        op.add_column("stories", sa.Column("product_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    pass  # a repair: nothing to undo
