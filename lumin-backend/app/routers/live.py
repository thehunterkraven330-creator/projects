"""Live shopping: merchants broadcast, anyone signed in can watch, chat and tap the products being shown.

Video goes through LiveKit (app/live.py mints the tokens); everything else — who is live, the chat, how many are watching — lives
here in plain database rows, so it works the same whatever carries the video."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import blocking, live
from app.auth import get_current_active_user
from app.auth.dependencies import get_optional_user
from app.database import get_db
from app.models import LiveMessage, LiveStream, LiveUserAction, LiveViewer, Notification, NotificationType, Product, User, follows
from app.rate_limit import limiter
from app.schemas import ProductRead

router = APIRouter(prefix="/live", tags=["live"])

# Host's browser pings every ~20s; no ping for this long = the broadcast is over (tab closed, signal lost).
HOST_TIMEOUT = timedelta(seconds=75)
# A viewer counts as "watching" if their screen refreshed within this window (it refreshes every ~2s).
VIEWER_WINDOW = timedelta(seconds=30)
MAX_PRODUCTS = 12
# How long a recording stays in the Recent lives list.
REPLAY_WINDOW = timedelta(days=7)


class LiveStartRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_PRODUCTS)


class LiveMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=300)


class LiveHearts(BaseModel):
    count: int = Field(ge=1, le=30)


class LiveStreamRead(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    host_id: uuid.UUID
    host_name: str
    host_avatar_url: str | None
    business_name: str | None
    started_at: datetime
    viewer_count: int
    replay_url: str | None = None
    thumbnail_url: str | None = None
    products: list[ProductRead] = []


class LiveJoin(BaseModel):
    url: str
    token: str
    stream: LiveStreamRead
    is_host: bool


class LiveMessageRead(BaseModel):
    id: int
    user_id: uuid.UUID | None
    name: str
    avatar_url: str | None
    body: str
    is_host: bool
    created_at: datetime


class LiveChatPage(BaseModel):
    status: str
    viewer_count: int
    hearts: int = 0
    messages: list[LiveMessageRead]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_configured() -> None:
    if live.config() is None:
        raise HTTPException(status_code=503, detail="Live isn't set up yet.")


def _viewer_count(db: Session, stream_id) -> int:
    return (
        db.query(func.count(LiveViewer.user_id))
        .filter(LiveViewer.stream_id == stream_id, LiveViewer.last_seen_at >= _now() - VIEWER_WINDOW)
        .scalar()
        or 0
    )


def _end(db: Session, stream: LiveStream) -> None:
    if stream.status != "ended":
        stream.status = "ended"
        stream.ended_at = _now()
        # Recorded lives get their replay link now; the file itself finishes a few seconds after the room closes.
        if stream.egress_id and live.recording_enabled():
            stream.replay_url = live.replay_url(stream.id)
        db.commit()
        if stream.egress_id:
            live.stop_recording(stream.egress_id)
            if stream.replay_url:
                # A minute or so on, when the recording is finished, a job shrinks it (retried while it is not ready).
                from app import jobs

                job = jobs.enqueue(db, jobs.OPTIMIZE_LIVE_REPLAY, {"stream_id": str(stream.id)}, delay_s=90)
                job.max_attempts = 6
                db.commit()
        live.close_room(stream.room_name)


def _expire_stale(db: Session) -> None:
    """Streams whose host went quiet are over. Done whenever the list is read, so there is nothing to schedule."""
    stale = db.query(LiveStream).filter(LiveStream.status == "live", LiveStream.last_seen_at < _now() - HOST_TIMEOUT).all()
    for s in stale:
        _end(db, s)


def _read(db: Session, s: LiveStream) -> LiveStreamRead:
    merchant = s.host.merchant_account
    return LiveStreamRead(
        id=s.id,
        title=s.title,
        status=s.status,
        host_id=s.host_id,
        host_name=s.host.display_name,
        host_avatar_url=s.host.avatar_url,
        business_name=merchant.business_name if merchant else None,
        started_at=s.started_at,
        viewer_count=_viewer_count(db, s.id) if s.status == "live" else 0,
        replay_url=s.replay_url if s.status == "ended" else None,
        thumbnail_url=s.thumbnail_url,
        products=[ProductRead.model_validate(p) for p in s.products],
    )


def _get_live(db: Session, stream_id: uuid.UUID) -> LiveStream:
    s = db.get(LiveStream, stream_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Live not found")
    if s.status == "live" and s.last_seen_at < _now() - HOST_TIMEOUT:
        _end(db, s)
    return s


def _check_not_blocked(db: Session, user: User, s: LiveStream) -> None:
    if blocking.applies_to(user) and blocking.is_blocked_between(db, user.id, s.host_id):
        raise HTTPException(status_code=403, detail="You can't join this live")


def _action_of(db: Session, s: LiveStream, user_id: uuid.UUID) -> str | None:
    """What the host did about this person in this live: 'mute', 'block' or None."""
    a = db.get(LiveUserAction, (s.id, user_id))
    return a.kind if a is not None else None


class LiveModerate(BaseModel):
    user_id: uuid.UUID
    action: str = Field(pattern="^(mute|block|clear)$")


# Followers hear about a live once per this long per host, so ending and restarting does not spam them.
NOTIFY_COOLDOWN = timedelta(minutes=30)
MAX_NOTIFIED = 5000


def _tell_followers(db: Session, host: User, stream: LiveStream) -> None:
    recent = (
        db.query(Notification.id)
        .filter(
            Notification.actor_id == host.id,
            Notification.type == NotificationType.live,
            Notification.created_at >= _now() - NOTIFY_COOLDOWN,
        )
        .first()
    )
    if recent is not None:
        return
    q = db.query(follows.c.follower_id).filter(follows.c.followee_id == host.id)
    if blocking.applies_to(host):
        q = q.filter(blocking.not_hidden(follows.c.follower_id, host.id))
    body = f"{host.display_name} is live: {stream.title}"[:200]
    for (follower_id,) in q.limit(MAX_NOTIFIED).all():
        db.add(Notification(user_id=follower_id, body=body, type=NotificationType.live, target_id=stream.id, actor_id=host.id))
    db.commit()


@router.post("", response_model=LiveJoin, status_code=201)
def start_live(body: LiveStartRequest, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    _require_configured()
    merchant = current_user.merchant_account
    if merchant is None:
        raise HTTPException(status_code=403, detail="Only business accounts can go live")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Give your live a title")

    # One live at a time per host: starting again ends the old one (e.g. the tab was closed without ending it).
    for old in db.query(LiveStream).filter(LiveStream.host_id == current_user.id, LiveStream.status == "live").all():
        _end(db, old)

    products = []
    if body.product_ids:
        products = (
            db.query(Product).filter(Product.id.in_(body.product_ids), Product.merchant_id == merchant.id).all()
        )
        if len(products) != len(set(body.product_ids)):
            raise HTTPException(status_code=422, detail="You can only show your own products")

    stream = LiveStream(host_id=current_user.id, title=title, room_name=f"live-{uuid.uuid4().hex[:16]}")
    stream.products = products
    db.add(stream)
    db.commit()
    db.refresh(stream)

    _tell_followers(db, current_user, stream)

    token = live.make_token(room=stream.room_name, identity=str(current_user.id), name=current_user.display_name, publish=True)
    return LiveJoin(url=live.config()[0], token=token, stream=_read(db, stream), is_host=True)


@router.get("", response_model=list[LiveStreamRead])
def list_live(current_user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    _expire_stale(db)
    q = db.query(LiveStream).filter(LiveStream.status == "live")
    if blocking.applies_to(current_user):
        q = q.filter(blocking.not_hidden(LiveStream.host_id, current_user.id))
    streams = q.order_by(LiveStream.started_at.desc()).limit(60).all()
    reads = [_read(db, s) for s in streams]
    reads.sort(key=lambda r: (-r.viewer_count, -r.started_at.timestamp()))
    return reads


def _frame_from_recording(s: LiveStream) -> None:
    """A recorded live that never got a still (it ended before one was taken, or is older than this feature) gets one cut from
    its recording. Best effort and quick: a recording that is not finished yet, or any failure, just leaves it for a later look."""
    import subprocess

    if not s.replay_url or s.thumbnail_url:
        return
    try:
        from app import storage

        for at in ("3", "0"):
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", at, "-i", s.replay_url, "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", "-f", "mjpeg", "-"],
                capture_output=True,
                timeout=25,
            )
            if out.returncode == 0 and out.stdout[:3] == b"\xff\xd8\xff":
                url = storage.put_public(f"live/{s.id}-thumb.jpg", out.stdout, "image/jpeg")
                s.thumbnail_url = f"{url}?v={int(_now().timestamp())}"
                return
    except Exception:  # noqa: BLE001
        return


@router.get("/replays", response_model=list[LiveStreamRead])
def list_replays(current_user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """Recently ended lives that were recorded, newest first."""
    q = db.query(LiveStream).filter(
        LiveStream.status == "ended",
        LiveStream.replay_url.isnot(None),
        LiveStream.ended_at >= _now() - REPLAY_WINDOW,
    )
    if blocking.applies_to(current_user):
        q = q.filter(blocking.not_hidden(LiveStream.host_id, current_user.id))
    rows = q.order_by(LiveStream.ended_at.desc()).limit(30).all()
    # Fill in missing pictures a few at a time, so one visit never waits long; the rest are filled on the next visits.
    made = 0
    for s in rows:
        if made >= 3:
            break
        if not s.thumbnail_url and s.ended_at and s.ended_at <= _now() - timedelta(minutes=2):
            _frame_from_recording(s)
            made += 1
    if made:
        db.commit()
    return [_read(db, s) for s in rows]


@router.get("/{stream_id}", response_model=LiveStreamRead)
def read_live(stream_id: uuid.UUID, db: Session = Depends(get_db)):
    return _read(db, _get_live(db, stream_id))


@router.post("/{stream_id}/join", response_model=LiveJoin)
def join_live(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    _require_configured()
    s = _get_live(db, stream_id)
    if s.status != "live":
        raise HTTPException(status_code=409, detail="This live has ended")
    _check_not_blocked(db, current_user, s)
    if _action_of(db, s, current_user.id) == "block":
        raise HTTPException(status_code=403, detail="The host removed you from this live")
    is_host = s.host_id == current_user.id
    token = live.make_token(room=s.room_name, identity=str(current_user.id), name=current_user.display_name, publish=is_host)
    return LiveJoin(url=live.config()[0], token=token, stream=_read(db, s), is_host=is_host)


@router.post("/{stream_id}/heartbeat")
def host_heartbeat(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = _get_live(db, stream_id)
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can do this")
    if s.status != "live":
        return {"status": "ended"}
    s.last_seen_at = _now()
    count = _viewer_count(db, s.id)
    s.peak_viewers = max(s.peak_viewers or 0, count)
    db.commit()
    return {"status": "live", "viewer_count": count}


MAX_THUMB_BYTES = 400_000
# Lives are longer than feed videos; the marked copy is made for recordings up to this long (longer ones save as the plain file).
LIVE_MARK_MAX_SECONDS = 15 * 60


@router.post("/{stream_id}/thumbnail")
async def set_thumbnail(
    stream_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The host's browser sends a JPEG still of its own video (raw request body) every so often while live; the newest one is the
    tile's picture. Best effort: a failure here must never matter to the broadcast."""
    s = db.get(LiveStream, stream_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Live not found")
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can do this")
    data = await request.body()
    if not data or len(data) > MAX_THUMB_BYTES or data[:3] != b"\xff\xd8\xff":
        raise HTTPException(status_code=422, detail="Send a JPEG picture under 400 KB")
    from app import storage  # imported here: it reads the storage settings when loaded

    try:
        url = storage.put_public(f"live/{s.id}-thumb.jpg", data, "image/jpeg")
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Could not save the picture")
    # A fresh query string each time, so viewers' browsers and the CDN do not keep showing the previous frame.
    s.thumbnail_url = f"{url}?v={int(_now().timestamp())}"
    db.commit()
    return {"thumbnail_url": s.thumbnail_url}


@router.delete("/{stream_id}", status_code=204)
def delete_stream(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The host removes a recorded live (the replay and its picture). Only after it has ended."""
    s = db.get(LiveStream, stream_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Live not found")
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can remove this")
    if s.status != "ended":
        raise HTTPException(status_code=409, detail="End the live first")
    urls = [s.replay_url, s.thumbnail_url.split("?")[0] if s.thumbnail_url else None]
    s.replay_url = None
    s.thumbnail_url = None
    db.commit()
    try:
        from app import storage

        storage.delete_view_urls(urls)
    except Exception:  # noqa: BLE001
        pass
    return Response(status_code=204)


class WatermarkedLive(BaseModel):
    url: str | None = None
    reason: str = "ok"


@router.post("/{stream_id}/watermarked-download", response_model=WatermarkedLive)
def watermarked_download(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The host's saved copy of a recording: the platform's mark and an end card burned in, exactly like a feed video's saved
    copy (app/watermark.py). url is null when it cannot be made (too long, still being prepared...): the app then saves the
    plain recording instead, and `reason` says why."""
    s = db.get(LiveStream, stream_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Live not found")
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can save this")
    if s.status != "ended" or not s.replay_url:
        return WatermarkedLive(url=None, reason="this live has no recording")
    handle = (s.host.display_name or "").strip() or "lumin"
    replay_url = s.replay_url
    db.close()  # the encode can take a while: do not hold a database connection for it
    from app import watermark
    from app.routers.video_posts import _WATERMARK_SLOTS

    if not _WATERMARK_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Busy preparing other downloads, try again in a moment.")
    try:
        url, reason = watermark.watermarked_url(replay_url, handle, max_seconds=LIVE_MARK_MAX_SECONDS)
        return WatermarkedLive(url=url, reason=reason)
    finally:
        _WATERMARK_SLOTS.release()


@router.post("/{stream_id}/moderate", status_code=204)
def moderate(
    stream_id: uuid.UUID,
    body: LiveModerate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The host mutes a person (their chat is hidden and they cannot write), blocks them (also removed from the live and kept
    out), or clears either. Only for this live."""
    s = _get_live(db, stream_id)
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can do this")
    if body.user_id == s.host_id:
        raise HTTPException(status_code=422, detail="You can't do that to yourself")
    row = db.get(LiveUserAction, (s.id, body.user_id))
    if body.action == "clear":
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(LiveUserAction(stream_id=s.id, user_id=body.user_id, kind=body.action))
    else:
        row.kind = body.action
    db.commit()
    if body.action == "block" and s.status == "live":
        live.remove_participant(s.room_name, str(body.user_id))
    return Response(status_code=204)


class ModeratedPerson(BaseModel):
    user_id: uuid.UUID
    name: str
    avatar_url: str | None
    kind: str


@router.get("/{stream_id}/moderation", response_model=list[ModeratedPerson])
def list_moderated(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The people the host has muted or removed from this live, so the host can undo it."""
    s = _get_live(db, stream_id)
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can see this")
    rows = db.query(LiveUserAction).filter(LiveUserAction.stream_id == s.id).order_by(LiveUserAction.created_at.desc()).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_([r.user_id for r in rows])).all()} if rows else {}
    return [
        ModeratedPerson(
            user_id=r.user_id,
            name=users[r.user_id].display_name if r.user_id in users else "Deleted user",
            avatar_url=users[r.user_id].avatar_url if r.user_id in users else None,
            kind=r.kind,
        )
        for r in rows
    ]


@router.post("/{stream_id}/end", status_code=204)
def end_live(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = db.get(LiveStream, stream_id)
    if s is None:
        return
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can end this live")
    _end(db, s)


@router.get("/{stream_id}/messages", response_model=LiveChatPage)
def read_messages(
    stream_id: uuid.UUID,
    after: int = Query(0, ge=0),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Polled every ~2s by everyone watching: new chat lines since `after`, the live/ended state and the watching count. The poll
    itself is what marks a signed-in viewer as present."""
    s = _get_live(db, stream_id)
    if s.status == "live" and current_user is not None and current_user.id != s.host_id:
        db.execute(
            pg_insert(LiveViewer)
            .values(stream_id=s.id, user_id=current_user.id, last_seen_at=_now())
            .on_conflict_do_update(index_elements=["stream_id", "user_id"], set_={"last_seen_at": _now()})
        )
        db.commit()
    q = db.query(LiveMessage).filter(LiveMessage.stream_id == s.id, LiveMessage.id > after)
    if current_user is not None and current_user.id != s.host_id and _action_of(db, s, current_user.id) == "block":
        raise HTTPException(status_code=403, detail="The host removed you from this live")
    # What the host muted or blocked is not shown to anyone (the host sees it only while moderating, via the chat they already have).
    hidden = db.query(LiveUserAction.user_id).filter(LiveUserAction.stream_id == s.id)
    q = q.filter(LiveMessage.user_id.is_(None) | LiveMessage.user_id.notin_(hidden))
    if blocking.applies_to(current_user):
        q = q.filter(blocking.not_hidden(LiveMessage.user_id, current_user.id) | (LiveMessage.user_id == s.host_id))
    rows = q.order_by(LiveMessage.id.asc()).limit(100).all()
    return LiveChatPage(
        status=s.status,
        viewer_count=_viewer_count(db, s.id) if s.status == "live" else 0,
        hearts=s.heart_count or 0,
        messages=[
            LiveMessageRead(
                id=m.id,
                user_id=m.user_id,
                name=m.user.display_name if m.user else "Deleted user",
                avatar_url=m.user.avatar_url if m.user else None,
                body=m.body,
                is_host=m.user_id == s.host_id,
                created_at=m.created_at,
            )
            for m in rows
        ],
    )


@router.post("/{stream_id}/messages", response_model=LiveMessageRead, status_code=201)
@limiter.limit("30/minute")
def send_message(
    request: Request,
    stream_id: uuid.UUID,
    body: LiveMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    s = _get_live(db, stream_id)
    if s.status != "live":
        raise HTTPException(status_code=409, detail="This live has ended")
    _check_not_blocked(db, current_user, s)
    if _action_of(db, s, current_user.id) is not None:
        raise HTTPException(status_code=403, detail="The host has turned off your chat in this live")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Write something first")
    m = LiveMessage(stream_id=s.id, user_id=current_user.id, body=text)
    db.add(m)
    db.commit()
    db.refresh(m)
    return LiveMessageRead(
        id=m.id,
        user_id=current_user.id,
        name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        body=m.body,
        is_host=current_user.id == s.host_id,
        created_at=m.created_at,
    )


@router.post("/{stream_id}/hearts", status_code=204)
@limiter.limit("120/minute")
def send_hearts(
    request: Request,
    stream_id: uuid.UUID,
    body: LiveHearts,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    s = _get_live(db, stream_id)
    if s.status != "live":
        return
    _check_not_blocked(db, current_user, s)
    db.query(LiveStream).filter(LiveStream.id == s.id).update({LiveStream.heart_count: LiveStream.heart_count + body.count})
    db.commit()


@router.post("/{stream_id}/recording", status_code=204)
def start_recording(stream_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The host's screen calls this once its camera is publishing (LiveKit can only record a room that exists). Safe to call again,
    and a recording that could not start leaves the live itself untouched."""
    s = _get_live(db, stream_id)
    if s.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can do this")
    if s.status != "live" or s.egress_id:
        return
    egress_id = live.start_recording(s.room_name, s.id)
    if egress_id:
        s.egress_id = egress_id
        db.commit()
