"""merchant: times a buyer reported nobody was there to meet them (collect in person)

Revision ID: 0055_collect_no_show_strikes
Revises: 0054_product_dimensions
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_collect_no_show_strikes"
down_revision = "0054_product_dimensions"
branch_labels = None
depends_on = None


def _has(column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("merchant_accounts")}


def upgrade() -> None:
    if not _has("collect_no_show_strikes"):
        op.add_column("merchant_accounts", sa.Column("collect_no_show_strikes", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if _has("collect_no_show_strikes"):
        op.drop_column("merchant_accounts", "collect_no_show_strikes")
