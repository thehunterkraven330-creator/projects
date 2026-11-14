"""merchant_accounts: pickup address (where a courier collects sealed orders)

Revision ID: 0047_merchant_pickup_address
Revises: 0046_stripe_connect
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0047_merchant_pickup_address"
down_revision = "0046_stripe_connect"
branch_labels = None
depends_on = None

COLUMNS = [
    ("pickup_contact_name", 100),
    ("pickup_phone", 30),
    ("pickup_line1", 200),
    ("pickup_line2", 200),
    ("pickup_city", 100),
    ("pickup_state", 100),
    ("pickup_postal_code", 20),
    ("pickup_country", 2),
]


def upgrade() -> None:
    # Idempotent: on a fresh database the baseline already built these from the models.
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("merchant_accounts")}
    for name, size in COLUMNS:
        if name not in have:
            op.add_column("merchant_accounts", sa.Column(name, sa.String(size), nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("merchant_accounts", name)
