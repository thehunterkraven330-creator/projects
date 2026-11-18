"""Stories: a picture or short clip that lasts 24 hours, from anyone, optionally with a product tagged."""
import uuid
from datetime import timezone
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app import blocking, storage, stories
from app.auth import get_current_active_user
from app.database import get_db
from app.models import MerchantAccount, Product, Story, StoryView, User, UserRole, follows
from app.rate_limit import limiter
from app.schemas import ProductRead, StoryAuthor, StoryCreate, StoryGroup, StoryRead, StoryReact, StoryRing, StoryViewer
from app.visibility import hide_shadow_banned_products

router = APIRouter(prefix="/stories", tags=["stories"])

MAX_GROUPS = 60


def _following_ids(db: Session, user: User) -> set:
    return {r[0] for r in db.query(follows.c.followee_id).filter(follows.c.follower_id == user.id)}


def _visible(db: Session, viewer: User, following: set):
    """SQL conditions for "this viewer may see this story right now"."""
    me = viewer.id
    is_admin = viewer.role == UserRole.admin
    conds = [Story.expires_at > stories.now()]
    if not is_admin:
        conds.append(or_(Story.moderation_hold.is_(False), Story.author_id == me))
        conds.append(or_(Story.author_id == me, blocking.not_hidden(Story.author_id, me)))
        conds.append(or_(Story.author_id == me, Story.audience == "everyone", and_(Story.audience == "followers", Story.author_id.in_(following or {uuid.UUID(int=0)}))))
    return conds


def _author(u: User) -> StoryAuthor:
    return StoryAuthor(id=u.id, username=u.username, display_name=u.display_name, avatar_url=u.avatar_url)


def _read_many(db: Session, viewer: User, rows: list[Story]) -> list[StoryRead]:
    if not rows:
        return []
    ids = [s.id for s in rows]
    my_views = {r[0]: r[1] for r in db.query(StoryView.story_id, StoryView.reaction).filter(StoryView.viewer_id == viewer.id, StoryView.story_id.in_(ids))}
    seen = set(my_views)
    mine = [s.id for s in rows if s.author_id == viewer.id]
    counts: dict = {}
    reacted: dict = {}
    if mine:
        from sqlalchemy import func

        counts = dict(db.query(StoryView.story_id, func.count()).filter(StoryView.story_id.in_(mine)).group_by(StoryView.story_id).all())
        reacted = dict(
            db.query(StoryView.story_id, func.count())
            .filter(StoryView.story_id.in_(mine), StoryView.reaction.isnot(None))
            .group_by(StoryView.story_id)
            .all()
        )
    pids = {s.product_id for s in rows if s.product_id}
    products: dict = {}
    if pids:
        q = db.query(Product).options(joinedload(Product.images)).filter(Product.id.in_(pids))
        products = {p.id: p for p in hide_shadow_banned_products(q, viewer).all()}
    out = []
    bought_cache: dict = {}
    for s in rows:
        p = products.get(s.product_id) if s.product_id else None
        if p is not None and s.author_id not in bought_cache:
            bought_cache[s.author_id] = stories.bought_by(db, s.author_id, {x.product_id for x in rows if x.author_id == s.author_id and x.product_id})
        out.append(
            StoryRead(
                id=s.id,
                author_id=s.author_id,
                media_url=s.media_url,
                media_type=s.media_type,
                caption=s.caption,
                product=ProductRead.model_validate(p) if p is not None else None,
                bought=bool(p is not None and p.id in bought_cache.get(s.author_id, set())),
                audience=s.audience,
                kind=s.kind or "post",
                event_at=s.event_at,
                created_at=s.created_at,
                expires_at=s.expires_at,
                seen=s.id in seen or s.author_id == viewer.id,
                views_count=counts.get(s.id, 0) if s.author_id == viewer.id else None,
                held=bool(s.moderation_hold) if s.author_id == viewer.id else False,
                my_reaction=my_views.get(s.id),
                reactions_count=reacted.get(s.id, 0) if s.author_id == viewer.id else None,
            )
        )
    return out


@router.get("", response_model=list[StoryGroup])
def story_tray(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The row of circles: my own stories, then people I follow who have one up. People with something I haven't seen come first."""
    following = _following_ids(db, current_user)
    authors = following | {current_user.id}
    rows = (
        db.query(Story)
        .filter(Story.author_id.in_(authors), *_visible(db, current_user, following))
        .order_by(Story.created_at.asc())
        .all()
    )
    reads = {r.id: r for r in _read_many(db, current_user, rows)}
    groups: "OrderedDict[uuid.UUID, list[StoryRead]]" = OrderedDict()
    for s in rows:
        groups.setdefault(s.author_id, []).append(reads[s.id])
    users = {u.id: u for u in db.query(User).filter(User.id.in_(list(groups.keys()))).all()} if groups else {}
    out = [
        StoryGroup(author=_author(users[a]), stories=items, has_unseen=any(not i.seen for i in items), is_me=(a == current_user.id))
        for a, items in groups.items()
        if a in users
    ]
    # You first, then people with something new, and within each of those the people you interact with most (likes, comments,
    # purchases, watching their updates...), then the newest. So the closest people are at the top, like other social apps.
    close = stories.engagement_scores(db, current_user.id, [g.author.id for g in out if not g.is_me])
    out.sort(key=lambda g: (not g.is_me, not g.has_unseen, -close.get(g.author.id, 0), -max(i.created_at for i in g.stories).timestamp()))
    return out[:MAX_GROUPS]


EXPLORE_MAX = 20


@router.get("/explore", response_model=list[StoryGroup])
def explore_stories(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Public updates from sellers I don't follow, so a new seller can be found: announcements first (a live or a sale that has not
    ended), then people with something I haven't seen, then the newest. Not people, only shops; never anyone I have blocked."""
    following = _following_ids(db, current_user)
    skip = following | {current_user.id}
    rows = (
        db.query(Story)
        .join(MerchantAccount, MerchantAccount.user_id == Story.author_id)
        .filter(Story.audience == "everyone", Story.author_id.notin_(skip), *_visible(db, current_user, following))
        .order_by(Story.created_at.asc())
        .limit(400)
        .all()
    )
    reads = {r.id: r for r in _read_many(db, current_user, rows)}
    groups: "OrderedDict[uuid.UUID, list[StoryRead]]" = OrderedDict()
    for s in rows:
        groups.setdefault(s.author_id, []).append(reads[s.id])
    users = {u.id: u for u in db.query(User).filter(User.id.in_(list(groups.keys()))).all()} if groups else {}
    now = stories.now()

    def announcing(items: list[StoryRead]) -> bool:
        return any(i.kind in ("live", "sale") and i.event_at is not None and i.event_at > now for i in items)

    out = [
        StoryGroup(author=_author(users[a]), stories=items, has_unseen=any(not i.seen for i in items), is_me=False)
        for a, items in groups.items()
        if a in users
    ]
    out.sort(key=lambda g: (not announcing(g.stories), not g.has_unseen, -max(i.created_at for i in g.stories).timestamp()))
    return out[:EXPLORE_MAX]


@router.get("/user/{user_id}", response_model=StoryGroup | None)
def user_stories(user_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """One person's stories (opened from their profile). Nothing (null) when they have none you may see."""
    following = _following_ids(db, current_user)
    rows = db.query(Story).filter(Story.author_id == user_id, *_visible(db, current_user, following)).order_by(Story.created_at.asc()).all()
    author = db.get(User, user_id)
    if not rows or author is None:
        return None
    items = _read_many(db, current_user, rows)
    return StoryGroup(author=_author(author), stories=items, has_unseen=any(not i.seen for i in items), is_me=(user_id == current_user.id))


@router.post("", response_model=StoryRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("12/minute")
def create_story(request: Request, payload: StoryCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if payload.media_type not in stories.MEDIA_TYPES or payload.audience not in stories.AUDIENCES:
        raise HTTPException(status_code=400, detail="That isn't a valid update.")
    key = storage.key_from_view_url(payload.media_url)
    if key is None or not storage.object_exists(key):
        raise HTTPException(status_code=400, detail="The picture or clip didn't upload. Please try again.")
    active = db.query(Story).filter(Story.author_id == current_user.id, Story.expires_at > stories.now()).count()
    if active >= stories.MAX_ACTIVE_PER_PERSON:
        raise HTTPException(status_code=429, detail=f"You have {stories.MAX_ACTIVE_PER_PERSON} updates up already. Delete one or wait for one to end.")
    product = None
    if payload.product_id is not None:
        product = db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="That product couldn't be found.")
    if payload.kind not in stories.KINDS:
        raise HTTPException(status_code=400, detail="That isn't a valid update.")
    event_at = None
    if payload.kind != "post":
        event_at = payload.event_at
        if event_at is None:
            raise HTTPException(status_code=400, detail="Pick the time for your announcement.")
        if event_at.tzinfo is None:
            event_at = event_at.replace(tzinfo=timezone.utc)
        if event_at <= stories.now():
            raise HTTPException(status_code=400, detail="That time has already passed.")
        if event_at > stories.now() + stories.EVENT_WINDOW:
            raise HTTPException(status_code=400, detail="Updates last 24 hours, so announce something that happens within the next 24 hours.")
        if payload.audience != "everyone":
            raise HTTPException(status_code=400, detail="Announcements are for everyone, so they can't be followers only.")
        if payload.kind == "sale":
            if payload.product_id is None:
                raise HTTPException(status_code=400, detail="Tag one of your own products for a flash sale.")
            # lock the product so two sales posted at once can't both start
            product = db.query(Product).filter(Product.id == payload.product_id).with_for_update().first()
            shop = current_user.merchant_account  # Product.merchant_id is the shop's id, not the person's
            if product is None or shop is None or product.merchant_id != shop.id:
                raise HTTPException(status_code=400, detail="Tag one of your own products for a flash sale.")
            pct = payload.sale_percent
            if pct is None or not stories.SALE_MIN_PERCENT <= pct <= stories.SALE_MAX_PERCENT:
                raise HTTPException(status_code=400, detail=f"Pick a sale discount from {stories.SALE_MIN_PERCENT}% to {stories.SALE_MAX_PERCENT}%.")
            if pct <= (product.discount_percent or 0):
                raise HTTPException(status_code=400, detail="A flash sale has to be a bigger discount than the product has now.")
            if not product.in_stock:
                raise HTTPException(status_code=400, detail="That product is out of stock.")
            if product.discount_ends_at is not None:
                raise HTTPException(status_code=409, detail="This product already has a flash sale running. Wait for it to end.")
        else:
            if current_user.merchant_account is None:
                raise HTTPException(status_code=400, detail="Only sellers can announce a live.")
            waiting = db.query(Story.id).filter(Story.author_id == current_user.id, Story.kind == "live", Story.event_at > stories.now(), Story.expires_at > stories.now()).first()
            if waiting is not None:
                raise HTTPException(status_code=409, detail="You already have a live announced. Delete it first to change the time.")
    caption = (payload.caption or "").strip() or None
    story = Story(
        kind=payload.kind,
        event_at=event_at,
        author_id=current_user.id,
        media_url=payload.media_url,
        media_type=payload.media_type,
        caption=caption,
        product_id=product.id if product else None,
        audience=payload.audience,
        expires_at=stories.now() + stories.LIFETIME,
    )
    db.add(story)
    if payload.kind == "sale" and product is not None:
        product.discount_restore_percent = product.discount_percent or 0  # what it goes back to
        product.discount_percent = payload.sale_percent
        product.discount_ends_at = event_at  # the sale ends by itself
    if payload.kind != "post" and story.audience == "everyone":
        db.flush()
        stories.tell_followers(db, current_user, story, product)
    db.commit()
    db.refresh(story)
    return _read_many(db, current_user, [story])[0]


def _visible_story(db: Session, viewer: User, story_id: uuid.UUID) -> Story:
    following = _following_ids(db, viewer)
    s = db.query(Story).filter(Story.id == story_id, *_visible(db, viewer, following)).first()
    if s is None:
        raise HTTPException(status_code=404, detail="This update is no longer available.")
    return s


@router.post("/{story_id}/view", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("120/minute")
def mark_seen(request: Request, story_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = _visible_story(db, current_user, story_id)
    if s.author_id != current_user.id and db.get(StoryView, (s.id, current_user.id)) is None:
        db.add(StoryView(story_id=s.id, viewer_id=current_user.id))
        try:
            db.commit()
        except Exception:
            db.rollback()  # two taps at once: the second insert loses, which is fine
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{story_id}/viewers", response_model=list[StoryViewer])
def story_viewers(story_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = db.get(Story, story_id)
    if s is None or s.author_id != current_user.id:
        raise HTTPException(status_code=404, detail="This update is no longer available.")
    rows = (
        db.query(StoryView, User)
        .join(User, User.id == StoryView.viewer_id)
        .filter(StoryView.story_id == s.id, blocking.not_hidden(StoryView.viewer_id, current_user.id))
        .order_by(StoryView.viewed_at.desc())
        .limit(300)
        .all()
    )
    return [StoryViewer(user=_author(u), viewed_at=v.viewed_at, reaction=v.reaction) for v, u in rows]


@router.post("/{story_id}/react", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
def react(request: Request, story_id: uuid.UUID, payload: StoryReact, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """React to a story with one emoji (or take it back with null). Reacting counts as having seen it."""
    if payload.emoji is not None and payload.emoji not in stories.REACTIONS:
        raise HTTPException(status_code=400, detail="That reaction isn't available.")
    s = _visible_story(db, current_user, story_id)
    if s.author_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't react to your own update.")
    row = db.get(StoryView, (s.id, current_user.id))
    if row is None:
        row = StoryView(story_id=s.id, viewer_id=current_user.id)
        db.add(row)
    row.reaction = payload.emoji
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/rings", response_model=list[StoryRing])
@limiter.limit("120/minute")
def story_rings(request: Request, ids: str = "", current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """For a batch of people (comma-separated ids, up to 60): which of them have a story this person may watch, and is
    there something new in it? People with none are left out. Used to draw the ring around avatars."""
    wanted: list[uuid.UUID] = []
    for raw in ids.split(",")[:60]:
        try:
            wanted.append(uuid.UUID(raw.strip()))
        except ValueError:
            continue
    if not wanted:
        return []
    following = _following_ids(db, current_user)
    rows = db.query(Story).filter(Story.author_id.in_(wanted), *_visible(db, current_user, following)).all()
    if not rows:
        return []
    seen = {r[0] for r in db.query(StoryView.story_id).filter(StoryView.viewer_id == current_user.id, StoryView.story_id.in_([s.id for s in rows]))}
    out: dict = {}
    for s in rows:
        new = s.author_id != current_user.id and s.id not in seen
        out[s.author_id] = out.get(s.author_id, False) or new
    return [StoryRing(user_id=u, has_unseen=n) for u, n in out.items()]


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story(story_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = db.get(Story, story_id)
    if s is None or (s.author_id != current_user.id and current_user.role != UserRole.admin):
        raise HTTPException(status_code=404, detail="This update is no longer available.")
    if s.kind == "sale" and s.product_id is not None:
        product = db.query(Product).filter(Product.id == s.product_id).with_for_update().first()
        if product is not None and product.discount_ends_at is not None and product.discount_ends_at == s.event_at:
            stories.finish_sale(product)  # taking the announcement down ends its sale
    stories.remove_files(s)
    db.delete(s)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
