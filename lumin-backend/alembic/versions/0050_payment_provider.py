"""payments: provider and currency per payment (the country decides which gateway and currency an order uses)

Revision ID: 0050_payment_provider
Revises: 0049_payout_attempts
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_payment_provider"
down_revision = "0049_payout_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: on a fresh database the baseline already built these from the model. Old rows stay NULL = "the deployment's
    # single provider" (app/payment_provider.py).
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("payments")}
    if "provider" not in have:
        op.add_column("payments", sa.Column("provider", sa.String(20), nullable=True))
    if "currency" not in have:
        op.add_column("payments", sa.Column("currency", sa.String(3), nullable=True))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("payments")}
    for col in ("currency", "provider"):
        if col in have:
            op.drop_column("payments", col)
