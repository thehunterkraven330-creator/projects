"""more product categories; fill in the person on old like/comment notices

Revision ID: 0062_more_categories_actor_backfill
Revises: 0061_notification_actor_backfill
Create Date: 2026-11-14
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0062_more_categories_actor_backfill"
down_revision = "0061_notification_actor_backfill"
branch_labels = None
depends_on = None

# Added next to Apparel / Electronics / Home & Living / Accessories. Names are chosen so the category icon rules
# (lumin-app/components/CategoryIcon.tsx) give each a fitting icon. A category that already exists is left alone, and
# the next app start gives each new one its general "All ..." collection (seed._ensure_default_collections).
NEW_CATEGORIES = [
    "Food & Drinks", "Groceries", "Beauty & Personal Care", "Health & Wellness", "Baby & Kids", "Sports & Fitness",
    "Books & Stationery", "Pets", "Toys & Games", "Automotive", "Garden & Plants", "Arts & Crafts", "Gifts & Occasions", "Tools",
]

# (notification type, text after the person's name, extra condition proving that person did the thing)
_BACKFILLS = [
    ("post_like", " liked your video.",
     "EXISTS (SELECT 1 FROM post_likes l WHERE l.user_id = u.id AND l.video_post_id = n.target_id)"),
    ("post_comment", " commented on your video.",
     "EXISTS (SELECT 1 FROM comments c WHERE c.author_id = u.id AND c.video_post_id = n.target_id AND c.parent_id IS NULL)"),
    ("comment_reply", " replied to your comment.",
     "EXISTS (SELECT 1 FROM comments c WHERE c.author_id = u.id AND c.video_post_id = n.target_id AND c.parent_id IS NOT NULL)"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name in NEW_CATEGORIES:
        bind.execute(
            sa.text("INSERT INTO categories (id, name) SELECT CAST(:id AS uuid), CAST(:name AS varchar) "
                "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = CAST(:name AS varchar))"),
            {"id": str(uuid.uuid4()), "name": name},
        )
    # Old like/comment/reply notices never recorded who did it, only the name in the text. Fill the person in only when it is
    # certain: exactly one user has that display name AND that user really did the like/comment on that video. Best effort: a
    # table or column that differs just skips that kind (each in its own savepoint), leaving those notices on the type icon.
    for ntype, tail, proof in _BACKFILLS:
        try:
            with bind.begin_nested():
                bind.execute(
                    sa.text(
                        "UPDATE notifications n SET actor_id = u.id FROM users u "
                        "WHERE n.actor_id IS NULL AND n.type::text = CAST(:t AS text) AND n.body = u.display_name || CAST(:tail AS text) "
                        "AND (SELECT count(*) FROM users u2 WHERE u2.display_name = u.display_name) = 1 AND " + proof
                    ),
                    {"t": ntype, "tail": tail},
                )
        except Exception:
            pass


def downgrade() -> None:
    pass
