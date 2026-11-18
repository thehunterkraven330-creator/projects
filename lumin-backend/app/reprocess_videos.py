"""Bring content uploaded before the quality update up to the new standard, without a traffic spike.

  python -m app.reprocess_videos --before 2026-11-01 --limit 50       feed videos: rebuild the streaming version
                                                                        (adds the 1080p rung when the source has it)
  python -m app.reprocess_videos --lives --limit 50                    live recordings still at the raw size

It only ADDS jobs to the queue (app/jobs.py); the worker does them one at a time, so run it in small batches and
let the queue drain. Nothing is lost if a job fails: the old file keeps playing. Run it again for the next batch with
--skip (the number already queued, newest first); a video already waiting in the queue is never queued twice. --dry-run only prints how many would be queued.
"""

import argparse
from datetime import datetime, timezone

from app import storage
from app.database import SessionLocal
from app.jobs import OPTIMIZE_LIVE_REPLAY, REBUILD_HLS, enqueue
from app.models import Job, LiveStream, VideoPost
from app.models.job import JOB_QUEUED, JOB_RUNNING


def _queued(db, kind: str, field: str) -> set[str]:
    rows = db.query(Job.payload).filter(Job.kind == kind, Job.status.in_((JOB_QUEUED, JOB_RUNNING))).all()
    return {r[0].get(field) for r in rows if r[0]}


def reprocess_posts(before: datetime, limit: int, dry: bool, skip: int = 0) -> int:
    db = SessionLocal()
    try:
        waiting = _queued(db, REBUILD_HLS, "post_id")
        q = (
            db.query(VideoPost)
            .filter(VideoPost.video_url.isnot(None), VideoPost.hls_url.isnot(None), VideoPost.created_at < before)
            .order_by(VideoPost.created_at.desc())
            .offset(skip)
        )
        n = 0
        for post in q:
            if str(post.id) in waiting:
                continue
            if n >= limit:
                break
            if not dry:
                enqueue(db, REBUILD_HLS, {"post_id": str(post.id)}, delay_s=n * 20)
            n += 1
        if not dry:
            db.commit()
        return n
    finally:
        db.close()


def reprocess_lives(limit: int, dry: bool) -> int:
    db = SessionLocal()
    try:
        waiting = _queued(db, OPTIMIZE_LIVE_REPLAY, "stream_id")
        n = 0
        for s in db.query(LiveStream).filter(LiveStream.status == "ended", LiveStream.replay_url.isnot(None)):
            key = storage.key_from_view_url(s.replay_url) or ""
            if not key.startswith("live/") or key.endswith("-hd.mp4") or str(s.id) in waiting:
                continue  # not ours, or already shrunk
            if n >= limit:
                break
            if not dry:
                enqueue(db, OPTIMIZE_LIVE_REPLAY, {"stream_id": str(s.id)}, delay_s=n * 20)
            n += 1
        if not dry:
            db.commit()
        return n
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", help="only videos uploaded before this date (YYYY-MM-DD)")
    ap.add_argument("--lives", action="store_true", help="live recordings instead of feed videos")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--skip", type=int, default=0, help="skip this many (newest first) already handled")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.lives:
        print("queued", reprocess_lives(a.limit, a.dry_run), "live recordings")
    elif a.before:
        cutoff = datetime.fromisoformat(a.before).replace(tzinfo=timezone.utc)
        print("queued", reprocess_posts(cutoff, a.limit, a.dry_run, a.skip), "videos")
    else:
        ap.print_help()
