"""orders: payout_attempts (failed bank payouts are retried with a fresh reference, never paid twice)

Revision ID: 0049_payout_attempts
Revises: 0048_product_weight
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_payout_attempts"
down_revision = "0048_product_weight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: on a fresh database the baseline already built this from the model.
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("orders")}
    if "payout_attempts" not in have:
        op.add_column("orders", sa.Column("payout_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("orders")}
    if "payout_attempts" in have:
        op.drop_column("orders", "payout_attempts")
