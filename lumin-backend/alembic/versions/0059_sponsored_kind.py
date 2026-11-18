"""sponsored twins: store the kind of product, so add-ons are picked in the database

Revision ID: 0059_sponsored_kind
Revises: 0058_raise_link_counts
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0059_sponsored_kind"
down_revision = "0058_raise_link_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("sponsored_twins")}
    if "kind" not in cols:
        op.add_column("sponsored_twins", sa.Column("kind", sa.String(24), nullable=True))
    if "ix_sponsored_twins_kind" not in {i["name"] for i in insp.get_indexes("sponsored_twins")}:
        op.create_index("ix_sponsored_twins_kind", "sponsored_twins", ["kind"])
    # Fill in the ones the product's own name settles. Anything not settled by the name stays NULL and is worked out (with the
    # description, section and AI reading) the first time it is a candidate, so a wrong guess here can never hide a product.
    try:
        from app import sponsored

        rows = bind.execute(
            sa.text("SELECT s.id, p.name FROM sponsored_twins s JOIN products p ON p.id = s.product_id WHERE s.kind IS NULL")
        ).fetchall()
        for sid, name in rows:
            kind = sponsored.kind_of(name)
            if kind:
                bind.execute(sa.text("UPDATE sponsored_twins SET kind = :k WHERE id = :i"), {"k": kind, "i": sid})
    except Exception:  # the fill is a speed-up only; the app works the same without it
        pass


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "ix_sponsored_twins_kind" in {i["name"] for i in insp.get_indexes("sponsored_twins")}:
        op.drop_index("ix_sponsored_twins_kind", table_name="sponsored_twins")
    if "kind" in {c["name"] for c in insp.get_columns("sponsored_twins")}:
        op.drop_column("sponsored_twins", "kind")
