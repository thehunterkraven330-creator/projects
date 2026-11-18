import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.auth import get_optional_user
from app.database import get_db
from app.models import Product, User, VideoFeed, VideoPost
from app.rate_limit import limiter
from app.routers.video_posts import _VIDEO_POST_LOAD_OPTIONS, _resolve_video_post_for_read
from app.schemas.catalog import ProductRead
from app.schemas.search import PersonResult, SearchResponse, SearchSection
from app.schemas.video import VideoPostRead
from app.twin_match import score_product, tokens
from app import blocking
from app.visibility import hide_held_posts, hide_shadow_banned, hide_shadow_banned_products

router = APIRouter(prefix="/search", tags=["search"])

SearchFilter = Literal["all", "people", "product", "feed", "discover"]

# How many product matches get ranked before paging (the rest sort after, by name).
_RANK_POOL = 300


class MentionPerson(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None


@router.get("/mentions", response_model=list[MentionPerson])
@limiter.limit("240/minute")
def mention_suggestions(
    request: Request,
    q: str = Query(..., min_length=1, max_length=40),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """The few people to offer while someone types "@ad" in a comment: usernames that start with what was typed first, then
    people whose display name starts with it (or has a word that does). Just enough to draw the list, no counts or bios, and a
    far higher limit than the full search since it runs as someone types. Blocked accounts never show (both ways)."""
    handle = q.strip().lstrip("@").strip()
    if not handle:
        return []
    esc = handle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    query = db.query(User).filter(
        or_(
            User.username.ilike(f"{esc}%", escape="\\"),
            User.display_name.ilike(f"{esc}%", escape="\\"),
            User.display_name.ilike(f"% {esc}%", escape="\\"),
        )
    )
    if blocking.applies_to(current_user):
        query = query.filter(blocking.not_hidden(User.id, current_user.id))
    return (
        query.order_by(
            case((func.lower(User.username) == handle.lower(), 0), (User.username.ilike(f"{esc}%", escape="\\"), 1), else_=2),
            User.username,
        )
        .limit(6)
        .all()
    )


@router.get("", response_model=SearchResponse)
@limiter.limit("30/minute")
def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    # Query alias keeps the wire-level param named `filter`, matching
    # SearchScreen.tsx's own `activeFilter`/FilterKey vocabulary, without
    # shadowing the `filter` builtin inside this function.
    filter_type: SearchFilter = Query(default="all", alias="filter"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Real backend text search + pagination for SearchScreen.tsx,
    replacing what used to be a client-side .filter() over whatever
    products/shopPosts/discoverPosts happened to already be loaded in
    memory for other screens entirely — fine at demo scale, not once the
    catalog or feeds actually grow past what's convenient to hold
    client-side.

    ILIKE substring matching rather than a real full-text index
    (to_tsvector/pg_trgm) — plenty for this catalog's size, and doesn't
    need a new Postgres extension enabled. Worth revisiting if the
    product/post count ever gets large enough for a substring scan on
    every keystroke to show up in latency.

    Still no auth *required* — current_user is optional, resolved only
    to feed the shadow-ban filters below (hide_shadow_banned/
    hide_shadow_banned_products, from app/visibility.py — same filtering
    list_video_posts/list_comments already apply, extended here to the
    other places a shadow-banned account's feed/discover/product results
    could otherwise surface). Search itself stays exactly as public as
    browsing the feeds or catalog directly already is. Rate-limited like
    discounts.py's preview route, since this runs one to four queries
    per request and a search box gets hit far more often than most
    other endpoints.

    People search is the one section below with no shadow-ban filter at
    all, by design — see visibility.py's own comment on why. A shadow
    ban is meant to be invisible to the banned person and starve their
    *content* of reach, not make the account itself unfindable, so
    searching a shadow-banned user's name still surfaces their profile
    even though none of their posts will ever turn up in the feed/
    discover sections below (or in the shop/discover feeds directly).
    """
    like = f"%{q}%"
    result = SearchResponse()

    # "@ada" looks people up by username: names that START with what follows the @ (exact match first), and nothing else. A bare
    # "@" has nothing to look up yet, so it finds nothing rather than listing everyone.
    if q.strip().startswith("@"):
        handle = q.strip()[1:].strip().lstrip("@")
        if handle and filter_type in ("all", "people"):
            escaped = handle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            people_query = db.query(User).filter(User.username.ilike(f"{escaped}%", escape="\\"))
            if blocking.applies_to(current_user):
                people_query = people_query.filter(blocking.not_hidden(User.id, current_user.id))
            result.people = SearchSection[PersonResult](
                items=people_query.order_by(
                    case((func.lower(User.username) == handle.lower(), 0), else_=1), User.username
                )
                .offset(offset)
                .limit(limit)
                .all(),
                total=people_query.count(),
            )
        return result

    if filter_type in ("all", "people"):
        people_query = db.query(User).filter(
            or_(User.username.ilike(like), User.display_name.ilike(like))
        )
        # No hide_shadow_banned_* call here — intentional, see this
        # route's own docstring.
        if blocking.applies_to(current_user):  # blocks hide accounts both ways (shadow bans, above, do not)
            people_query = people_query.filter(blocking.not_hidden(User.id, current_user.id))
        result.people = SearchSection[PersonResult](
            items=people_query.order_by(User.display_name).offset(offset).limit(limit).all(),
            total=people_query.count(),
        )

    if filter_type in ("all", "product"):
        products_query = db.query(Product).options(joinedload(Product.images)).filter(
            or_(Product.name.ilike(like), Product.description.ilike(like))
        )
        products_query = hide_shadow_banned_products(products_query, current_user)
        # Ranked, not alphabetical: how well the words fit the listing, plus a small
        # bonus for good photos and a real description (the SEO effect for merchants,
        # see app/twin_match.py). Ranks the first _RANK_POOL matches, then pages.
        q_tokens = tokens(q)
        pool = products_query.order_by(Product.name).limit(_RANK_POOL).all()
        if q_tokens:
            pool.sort(key=lambda p: (-score_product(q_tokens, p).rank, p.name))
        result.products = SearchSection[ProductRead](
            items=pool[offset : offset + limit],
            total=products_query.count(),
        )

    if filter_type in ("all", "feed"):
        feed_query = (
            db.query(VideoPost)
            .join(VideoPost.poster)
            .options(*_VIDEO_POST_LOAD_OPTIONS)
            .filter(VideoPost.feed == VideoFeed.shop)
            .filter(or_(VideoPost.retwin_kind.is_(None), VideoPost.retwin_kind != "product"))
            .filter(
                or_(
                    VideoPost.description.ilike(like),
                    User.username.ilike(like),
                    User.display_name.ilike(like),
                )
            )
        )
        feed_query = hide_shadow_banned(feed_query, VideoPost.poster, VideoPost.poster_id, current_user)
        feed_query = hide_held_posts(feed_query, current_user)
        result.feed = SearchSection[VideoPostRead](
            items=[
                _resolve_video_post_for_read(p)
                for p in feed_query.order_by(VideoPost.created_at.desc()).offset(offset).limit(limit).all()
            ],
            total=feed_query.count(),
        )

    if filter_type in ("all", "discover"):
        discover_query = (
            db.query(VideoPost)
            .join(VideoPost.poster)
            .options(*_VIDEO_POST_LOAD_OPTIONS)
            .filter(VideoPost.feed == VideoFeed.discover)
            .filter(
                or_(
                    VideoPost.description.ilike(like),
                    User.username.ilike(like),
                    User.display_name.ilike(like),
                )
            )
        )
        discover_query = hide_shadow_banned(
            discover_query, VideoPost.poster, VideoPost.poster_id, current_user
        )
        discover_query = hide_held_posts(discover_query, current_user)
        result.discover = SearchSection[VideoPostRead](
            items=[
                _resolve_video_post_for_read(p)
                for p in discover_query.order_by(VideoPost.created_at.desc()).offset(offset).limit(limit).all()
            ],
            total=discover_query.count(),
        )

    return result
