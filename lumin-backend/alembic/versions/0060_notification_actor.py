"""notifications: who caused it, and whether it is about the business account

Revision ID: 0060_notification_actor
Revises: 0059_sponsored_kind
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0060_notification_actor"
down_revision = "0059_sponsored_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("notifications")}
    if "actor_id" not in cols:
        op.add_column(
            "notifications",
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
    if "audience" not in cols:
        op.add_column("notifications", sa.Column("audience", sa.String(12), nullable=True))
    # Old order notices that went to a seller (the person owns a business account that has the product) are marked now,
    # so they open the business Orders too. The old rows never recorded the order, so this is by wording only and errs
    # on the side of leaving a notice personal.
    op.execute(
        "UPDATE notifications SET audience = 'seller' WHERE audience IS NULL AND type = 'order' AND ("
        "body LIKE 'The buyer %' OR body LIKE '%plans to come and collect%' OR body LIKE 'A payout for order %' "
        "OR body LIKE '%was delivered. Payment is released%' OR body LIKE 'A driver collected order %' "
        "OR body LIKE '%is sealed and waiting for a driver%' OR body LIKE '%was refunded to the buyer%' "
        "OR body LIKE '%must be ready for pickup%' OR body LIKE '%no driver has collected it%' "
        "OR body LIKE 'The courier cancelled the pickup%' OR body LIKE '%was cancelled and refunded because it wasn''t marked ready%')"
    )


def downgrade() -> None:
    op.drop_column("notifications", "audience")
    op.drop_column("notifications", "actor_id")
