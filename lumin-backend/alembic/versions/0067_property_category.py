"""a Property & Rentals category (homes, flats, land, shops to rent or buy)

Revision ID: 0067_property_category
Revises: 0066_live_user_actions
Create Date: 2026-11-15
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0067_property_category"
down_revision = "0066_live_user_actions"
branch_labels = None
depends_on = None

NAME = "Property & Rentals"


def upgrade() -> None:
    # Left alone if it already exists; the next app start gives it its general "All ..." collection
    # (seed._ensure_default_collections), like the categories added in 0062.
    op.get_bind().execute(
        sa.text("INSERT INTO categories (id, name) SELECT CAST(:id AS uuid), CAST(:name AS varchar) "
                "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = CAST(:name AS varchar))"),
        {"id": str(uuid.uuid4()), "name": NAME},
    )


def downgrade() -> None:
    pass
