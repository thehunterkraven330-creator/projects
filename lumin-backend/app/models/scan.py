import uuid
from datetime import datetime

from sqlalchemy import false as sa_false
from sqlalchemy import Boolean, event, func, select, update, DateTime, Float, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk

FLAG_OPEN = "open"
FLAG_DISMISSED = "dismissed"
FLAG_CONFIRMED = "confirmed"
FINGERPRINT_OK = "ok"
FINGERPRINT_FAILED = "failed"


class VideoFingerprint(Base, TimestampMixin):
    """What "scan a video" searches: the sound / picture fingerprints of one uploaded video (app/scan_fp.py).
    `video_url` records which file was fingerprinted - after a post's video is replaced the old row no longer
    counts (and is rebuilt). `created_at` is also the platform's first-seen time for this video."""

    __tablename__ = "video_fingerprints"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_posts.id", ondelete="CASCADE"), unique=True
    )
    video_url: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12), default=FINGERPRINT_OK)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Set when this upload is a whole-video copy of an earlier post (same poster re-uploading, or another poster).
    # Copies are not searched themselves: a scan finds the ORIGINAL post and lists the copies' products with it
    # (app/scan_service.py). Cleared (SET NULL) if the original is deleted, which makes the copy searchable again.
    # False for fingerprints made before copies were grouped: the worker checks them once when idle (relink_one).
    copy_checked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    dup_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_posts.id", ondelete="SET NULL"), nullable=True, index=True
    )


class VideoScan(Base, TimestampMixin):
    """One lookup: someone scanned a recording. Powers "how many people scanned your video"."""

    __tablename__ = "video_scans"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str | None] = mapped_column(String(60), nullable=True)
    clip_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Who is behind a signed-out scan, for the public search count: the app's browser/phone id and a salted hash of the network address.
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True when this scan added one to the video's public search count.
    counted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())


class VideoMatchFlag(Base, TimestampMixin):
    """A later upload that looks like an earlier one from a DIFFERENT poster. Created automatically when the
    later video is fingerprinted; an admin dismisses it (not the same video) or confirms it (it is). Nothing
    is removed automatically - this is a review queue, and nothing is shown to buyers or viewers."""

    __tablename__ = "video_match_flags"
    __table_args__ = (UniqueConstraint("video_post_id", "earlier_post_id", name="uq_match_flag_pair"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    video_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_posts.id", ondelete="CASCADE"), index=True
    )
    earlier_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_posts.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(12), default=FLAG_OPEN, index=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProductVisual(Base, TimestampMixin):
    """A product photo turned into a small vector, for "find similar" on the Found it screen (app/visual_index.py).
    `kind` says how the vector was made (a picture model, or the built-in colour/edge layout); vectors of different
    kinds are never compared. `image_url` records which photo was described: when the product's first photo changes,
    the row is rebuilt."""

    __tablename__ = "product_visuals"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    image_url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    vec: Mapped[bytes] = mapped_column(LargeBinary)


# Most signed-out searches one network address can add to public counts in a day (a shared office or mobile network has many people
# behind it, so this is generous; it only stops one place from running up numbers).
SIGNED_OUT_COUNTS_PER_IP_PER_DAY = 20


@event.listens_for(VideoScan, "before_insert")
def _decide_if_counted(mapper, connection, target):
    """Decide whether a found scan adds to the video's public "Lumin search count" (VideoPost.scans_count).

    The count is meant to be genuine, like likes:
      - a signed-in person counts once per video, however often they scan it; the poster never counts;
      - someone not signed in counts once per device (X-Device-Id) per video, and one network address can add only
        SIGNED_OUT_COUNTS_PER_IP_PER_DAY such searches a day; with no device id they do not count.
    Every scan is still kept for the seller's own analytics; only this public number is limited."""
    from datetime import timedelta, timezone

    from . import video as _video
    from app import scan_origin

    device, ip_hash = scan_origin.current.get()
    if target.device_id is None:
        target.device_id = device if target.user_id is None else None
    if target.ip_hash is None:
        target.ip_hash = ip_hash
    target.counted = False
    if not target.found or target.video_post_id is None:
        return
    VideoPost = _video.VideoPost
    poster_id = connection.execute(select(VideoPost.poster_id).where(VideoPost.id == target.video_post_id)).scalar()
    if poster_id is None or poster_id == target.user_id:
        return
    if target.user_id is not None:
        who = VideoScan.user_id == target.user_id
    else:
        if not target.device_id:
            return
        who = (VideoScan.user_id.is_(None)) & (VideoScan.device_id == target.device_id)
        if target.ip_hash:
            since = datetime.now(timezone.utc) - timedelta(days=1)
            today = connection.execute(
                select(func.count())
                .select_from(VideoScan)
                .where(VideoScan.ip_hash == target.ip_hash, VideoScan.counted.is_(True), VideoScan.user_id.is_(None), VideoScan.created_at >= since)
            ).scalar()
            if (today or 0) >= SIGNED_OUT_COUNTS_PER_IP_PER_DAY:
                return
    already = connection.execute(
        select(VideoScan.id).where(VideoScan.video_post_id == target.video_post_id, VideoScan.found.is_(True), who).limit(1)
    ).first()
    if already:
        return
    target.counted = True


@event.listens_for(VideoScan, "after_insert")
def _count_found_scan(mapper, connection, target):
    """Add one to the video's public search count when the scan was decided to count (see above)."""
    if target.counted and target.video_post_id is not None:
        from .video import VideoPost

        connection.execute(
            update(VideoPost).where(VideoPost.id == target.video_post_id).values(scans_count=VideoPost.scans_count + 1)
        )
