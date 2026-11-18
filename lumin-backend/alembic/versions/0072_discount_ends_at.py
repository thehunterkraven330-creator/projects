"""a product discount can end by itself (flash sale stories)

Revision ID: 0072_discount_ends_at
Revises: 0071_story_announcements
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0072_discount_ends_at"
down_revision = "0071_story_announcements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("discount_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("discount_restore_percent", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "discount_restore_percent")
    op.drop_column("products", "discount_ends_at")
