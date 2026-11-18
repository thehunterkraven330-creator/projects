"""products: shipping weight in grams (the courier's rate depends on it)

Revision ID: 0048_product_weight
Revises: 0047_merchant_pickup_address
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0048_product_weight"
down_revision = "0047_merchant_pickup_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: on a fresh database the baseline already built this from the model.
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("products")}
    if "weight_grams" not in have:
        op.add_column("products", sa.Column("weight_grams", sa.Integer(), nullable=True))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("products")}
    if "weight_grams" in have:
        op.drop_column("products", "weight_grams")
