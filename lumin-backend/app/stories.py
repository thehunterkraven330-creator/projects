"""Stories: a picture or short clip that lasts 24 hours. Rules in one place; the endpoints are in app/routers/stories.py."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import storage
from app.models import (
    Comment,
    MerchantAccount,
    Order,
    OrderStatus,
    Product,
    Report,
    ReportTargetType,
    Story,
    StoryView,
    VideoPost,
    VideoView,
    post_likes,
    post_shares,
    watchlist_items,
)

log = logging.getLogger("lumin")

LIFETIME = timedelta(hours=24)
MAX_ACTIVE_PER_PERSON = 30
CAPTION_MAX = 200
AUDIENCES = ("everyone", "followers")
MEDIA_TYPES = ("image", "video")
KINDS = ("post", "live", "sale")
# An announcement is for the next 24 hours, the same as the story itself.
EVENT_WINDOW = LIFETIME
REACTIONS = ("❤️", "😂", "😮", "😢", "🔥", "👏")
KEEP_AFTER_EXPIRY = timedelta(hours=1)  # a short grace so a viewer who opened it at 23:59 isn't cut off mid-clip


def now() -> datetime:
    return datetime.now(timezone.utc)


def bought_by(db: Session, author_id: uuid.UUID, product_ids: set) -> set:
    """Of these products, the ones `author_id` has really bought (an order that wasn't cancelled): they get the
    "Bought on Lumin" badge. Never claimed for a product the person only tagged."""
    if not product_ids:
        return set()
    rows = (
        db.query(Order.product_id)
        .filter(Order.buyer_id == author_id, Order.product_id.in_(product_ids), Order.status != OrderStatus.cancelled)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def on_report(db: Session, report: Report) -> None:
    """Enough different people reporting a story hides it until someone looks (the same threshold as videos). Caller commits."""
    threshold = int(os.environ.get("MODERATION_REPORT_HOLD", "3"))
    if threshold <= 0 or report.target_type != ReportTargetType.story:
        return
    from sqlalchemy import func

    n = (
        db.query(func.count(func.distinct(Report.reporter_id)))
        .filter(Report.target_type == ReportTargetType.story, Report.target_id == report.target_id, Report.reporter_id.isnot(None))
        .scalar()
    ) or 0
    story = db.get(Story, report.target_id)
    if story is not None and n >= threshold:
        story.moderation_hold = True


def remove_files(story: Story) -> None:
    key = storage.key_from_view_url(story.media_url)
    if key is None:
        return
    try:
        storage.delete_object(key)
    except Exception:
        log.warning("could not delete the file of story %s", story.id, exc_info=True)


def purge_expired(db: Session, limit: int = 200) -> int:
    """Delete stories that ended more than an hour ago, and their files. Run by the worker every few minutes."""
    old = db.query(Story).filter(Story.expires_at < now() - KEEP_AFTER_EXPIRY).limit(limit).all()
    for s in old:
        remove_files(s)
        db.delete(s)
    db.commit()
    return len(old)


SALE_MIN_PERCENT, SALE_MAX_PERCENT = 5, 90


def finish_sale(product: Product) -> None:
    """Put the product back as it was before its flash sale (its own discount, or none)."""
    product.discount_percent = product.discount_restore_percent or None
    product.discount_ends_at = None
    product.discount_restore_percent = None


def end_discounts(db: Session) -> int:
    """Finish the flash sales that have ended. The charge is already right the moment a sale ends (Product.sale_price looks at the
    time); this puts the discount back as it was so the badge goes too. Run by the worker every minute."""
    rows = db.query(Product).filter(Product.discount_ends_at.isnot(None), Product.discount_ends_at <= now()).limit(500).all()
    for p in rows:
        finish_sale(p)
    db.commit()
    return len(rows)


MAX_NOTIFIED = 500


def tell_followers(db: Session, author, story: Story, product=None) -> None:
    """A live or flash-sale announcement tells the people who follow the seller (not ordinary stories: that would be noise).
    The caller commits."""
    from app import blocking
    from app.models import Notification, NotificationType, follows

    q = db.query(follows.c.follower_id).filter(follows.c.followee_id == author.id)
    if blocking.applies_to(author):
        q = q.filter(blocking.not_hidden(follows.c.follower_id, author.id))
    if story.kind == "live" and story.event_at is not None:
        at = story.event_at.astimezone(timezone.utc).strftime("%H:%M UTC")
        body = f"{author.display_name} is going live at {at}"
    else:
        pct = product.discount_percent if product is not None else None
        body = f"{author.display_name} has a flash sale" + (f": {pct}% off {product.name}" if pct and product is not None else "")
    for (follower_id,) in q.limit(MAX_NOTIFIED).all():
        db.add(Notification(user_id=follower_id, body=body[:200], type=NotificationType.story, target_id=story.id, actor_id=author.id))


# How much each kind of interaction says "this person matters to me". Orders say the most, a like the least.
WEIGHT_ORDER = 8
WEIGHT_COMMENT = 5
WEIGHT_SAVE = 4
WEIGHT_REACTION = 4
WEIGHT_LIKE = 3
WEIGHT_SHARE = 3
WEIGHT_WATCHED = 1  # watched one of their videos to the end, or opened one of their updates


def engagement_scores(db: Session, viewer_id: uuid.UUID, author_ids) -> dict:
    """How much `viewer` interacts with each of `author_ids`: likes, shares, saves, comments, finished videos, bought from,
    watched or reacted to their updates. Higher = closer. Used to order the Updates list so the people you engage with most come
    first, the way other social apps rank them. One small query per signal, all at once for the whole list."""
    ids = list(author_ids)
    if not ids:
        return {}
    score: dict = {a: 0 for a in ids}

    def add(rows, weight: int) -> None:
        for author_id, n in rows:
            if author_id in score:
                score[author_id] += weight * int(n)

    for table, weight in ((post_likes, WEIGHT_LIKE), (post_shares, WEIGHT_SHARE), (watchlist_items, WEIGHT_SAVE)):
        add(
            db.query(VideoPost.poster_id, func.count())
            .select_from(table)
            .join(VideoPost, VideoPost.id == table.c.video_post_id)
            .filter(table.c.user_id == viewer_id, VideoPost.poster_id.in_(ids))
            .group_by(VideoPost.poster_id),
            weight,
        )
    add(
        db.query(VideoPost.poster_id, func.count())
        .select_from(Comment)
        .join(VideoPost, VideoPost.id == Comment.video_post_id)
        .filter(Comment.author_id == viewer_id, VideoPost.poster_id.in_(ids))
        .group_by(VideoPost.poster_id),
        WEIGHT_COMMENT,
    )
    add(
        db.query(VideoPost.poster_id, func.count())
        .select_from(VideoView)
        .join(VideoPost, VideoPost.id == VideoView.video_post_id)
        .filter(VideoView.viewer_id == viewer_id, VideoView.completed.is_(True), VideoPost.poster_id.in_(ids))
        .group_by(VideoPost.poster_id),
        WEIGHT_WATCHED,
    )
    add(
        db.query(Story.author_id, func.count())
        .select_from(StoryView)
        .join(Story, Story.id == StoryView.story_id)
        .filter(StoryView.viewer_id == viewer_id, Story.author_id.in_(ids))
        .group_by(Story.author_id),
        WEIGHT_WATCHED,
    )
    add(
        db.query(Story.author_id, func.count())
        .select_from(StoryView)
        .join(Story, Story.id == StoryView.story_id)
        .filter(StoryView.viewer_id == viewer_id, StoryView.reaction.isnot(None), Story.author_id.in_(ids))
        .group_by(Story.author_id),
        WEIGHT_REACTION,
    )
    add(  # things they bought from this seller
        db.query(MerchantAccount.user_id, func.count())
        .select_from(Order)
        .join(Product, Product.id == Order.product_id)
        .join(MerchantAccount, MerchantAccount.id == Product.merchant_id)
        .filter(Order.buyer_id == viewer_id, Order.status != OrderStatus.cancelled, MerchantAccount.user_id.in_(ids))
        .group_by(MerchantAccount.user_id),
        WEIGHT_ORDER,
    )
    return score
