"""collect in person: a claim is either "nobody was there" or "the seller refused to show or sell it"

Revision ID: 0057_collect_claim_kind
Revises: 0056_collect_no_shows
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0057_collect_claim_kind"
down_revision = "0056_collect_no_shows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("collect_no_shows")}
    if "kind" not in cols:
        op.add_column("collect_no_shows", sa.Column("kind", sa.String(16), nullable=False, server_default="not_there"))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("collect_no_shows")}
    if "kind" in cols:
        op.drop_column("collect_no_shows", "kind")
