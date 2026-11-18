"""like / share / save numbers never below the saved records behind them (one-off catch-up)

Older versions could save a like, share or save without moving its number, so the number shown after a reload was
too low while the icon (read from the saved record) stayed on. This raises each number to at least the count of
saved records. It only ever raises, so made-up demo numbers are left alone.

Revision ID: 0058_raise_link_counts
Revises: 0057_collect_claim_kind
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0058_raise_link_counts"
down_revision = "0057_collect_claim_kind"
branch_labels = None
depends_on = None

_PAIRS = (("likes_count", "post_likes"), ("shares_count", "post_shares"), ("saves_count", "watchlist_items"))


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "video_posts" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("video_posts")}
    for col, table in _PAIRS:
        if col in cols and table in tables:
            op.execute(
                f"UPDATE video_posts SET {col} = r.n FROM "
                f"(SELECT video_post_id, count(*) AS n FROM {table} GROUP BY video_post_id) r "
                f"WHERE r.video_post_id = video_posts.id AND video_posts.{col} < r.n"
            )


def downgrade() -> None:
    pass  # a catch-up of wrong numbers; nothing to undo
