"""product size in cm (volumetric weight, and the too-big-to-post rule)

Revision ID: 0054_product_dimensions
Revises: 0053_visiting_hours
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_product_dimensions"
down_revision = "0053_visiting_hours"
branch_labels = None
depends_on = None

_COLS = ("length_cm", "width_cm", "height_cm")


def _has(column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("products")}


def upgrade() -> None:
    for c in _COLS:
        if not _has(c):
            op.add_column("products", sa.Column(c, sa.Integer(), nullable=True))


def downgrade() -> None:
    for c in _COLS:
        if _has(c):
            op.drop_column("products", c)
