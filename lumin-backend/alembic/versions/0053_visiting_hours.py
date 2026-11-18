"""merchant visiting hours (when someone is there for buyers who collect in person)

Revision ID: 0053_visiting_hours
Revises: 0052_collect_in_person
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_visiting_hours"
down_revision = "0052_collect_in_person"
branch_labels = None
depends_on = None


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has("merchant_accounts", "pickup_visiting_hours"):
        op.add_column("merchant_accounts", sa.Column("pickup_visiting_hours", sa.String(200), nullable=True))


def downgrade() -> None:
    if _has("merchant_accounts", "pickup_visiting_hours"):
        op.drop_column("merchant_accounts", "pickup_visiting_hours")
