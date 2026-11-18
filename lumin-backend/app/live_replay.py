"""Shrinks a live's recording after the live ends.

LiveKit records in real time, which cannot compress well: the file comes out around 6 Mbps (2.7 GB an hour to watch). This
re-encodes it the slow, careful way (like the feed's videos), keeping the picture sharp at roughly a third to a half of the
size, and points the live's replay at the new file. Runs in the job queue (app/jobs.py) a minute or so after the live ends,
and retries while the recording is still being finished.
"""
import logging
import os
import subprocess
import tempfile
import uuid

from app import live, storage
from app.database import SessionLocal
from app.models import LiveStream

log = logging.getLogger("lumin")

# Short side of the picture (never upscaled), quality target, and a ceiling so a busy scene cannot make the file big.
SHORT_SIDE = 1080
CRF = "23"
MAXRATE = "3000k"
BUFSIZE = "6000k"
AUDIO = "96k"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def optimize_replay(stream_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        s = db.get(LiveStream, stream_id)
        if s is None or not s.replay_url:
            return  # removed by the host meanwhile
        key = live.replay_key(stream_id)
        if storage.key_from_view_url(s.replay_url) != key:
            return  # already the shrunk copy
        if not storage.object_exists(key):
            raise RuntimeError("recording not finished yet")
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.mp4")
            dst = os.path.join(tmp, "out.mp4")
            storage.download_object(key, src)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", src],
                capture_output=True, text=True, timeout=60,
            )
            if probe.returncode != 0 or not probe.stdout.strip():
                raise RuntimeError("recording not readable yet")
            scale = f"scale=w='if(gt(iw,ih),-2,min({SHORT_SIDE},iw))':h='if(gt(iw,ih),min({SHORT_SIDE},ih),-2)'"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", src, "-vf", scale,
                    "-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-crf", CRF,
                    "-maxrate", MAXRATE, "-bufsize", BUFSIZE, "-g", "60", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", AUDIO, "-ac", "2", "-movflags", "+faststart", dst,
                ],
                check=True, capture_output=True, timeout=1800,
            )
            # Only worth switching to when it really is smaller.
            if os.path.getsize(dst) >= os.path.getsize(src):
                return
            new_key = f"live/{stream_id}-hd.mp4"
            storage.upload_file(dst, new_key, "video/mp4", IMMUTABLE_CACHE)
        db.refresh(s)
        if s.replay_url and storage.key_from_view_url(s.replay_url) == key:
            s.replay_url = storage.view_url_for_key(new_key)
            db.commit()
            storage.delete_view_urls([storage.view_url_for_key(key)])
        else:
            storage.delete_view_urls([storage.view_url_for_key(new_key)])  # removed meanwhile
    finally:
        db.close()
