"""product_visuals: small picture vectors of product photos, for "find similar" on the Found it screen

Revision ID: 0068_product_visuals
Revises: 0067_property_category
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0068_product_visuals"
down_revision = "0067_property_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_visuals",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("vec", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_visuals_kind", "product_visuals", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_product_visuals_kind", table_name="product_visuals")
    op.drop_table("product_visuals")
