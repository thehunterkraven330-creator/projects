"""collect in person: a product flag and the order's visiting details

Revision ID: 0052_collect_in_person
Revises: 0051_shipment_bag_optional
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0052_collect_in_person"
down_revision = "0051_shipment_bag_optional"
branch_labels = None
depends_on = None


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has("products", "collect_in_person"):
        op.add_column("products", sa.Column("collect_in_person", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has("orders", "collect_in_person"):
        op.add_column("orders", sa.Column("collect_in_person", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has("orders", "visit_details"):
        op.add_column("orders", sa.Column("visit_details", sa.Text(), nullable=True))
    if not _has("orders", "visit_details_at"):
        op.add_column("orders", sa.Column("visit_details_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for t, c in (("orders", "visit_details_at"), ("orders", "visit_details"), ("orders", "collect_in_person"), ("products", "collect_in_person")):
        if _has(t, c):
            op.drop_column(t, c)
