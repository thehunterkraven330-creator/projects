"""shipments: the sealed bag is optional (an order without a live test is tracked by its courier alone)

Revision ID: 0051_shipment_bag_optional
Revises: 0050_payment_provider
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_shipment_bag_optional"
down_revision = "0050_payment_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("shipments")}
    if "bag_id" in cols and not cols["bag_id"]["nullable"]:
        op.alter_column("shipments", "bag_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    # Bagless shipments cannot be kept once the column is NOT NULL again.
    op.execute("DELETE FROM shipments WHERE bag_id IS NULL")
    op.alter_column("shipments", "bag_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
