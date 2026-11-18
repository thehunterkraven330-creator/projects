"""Live shopping: minting LiveKit access tokens. The video runs through LiveKit (livekit.io, cloud or self-hosted); this app never
touches the media, it only decides who may join which room and as what (host publishes, viewers only watch).

Env (all three needed, else the Live routes answer 503 "not set up yet"):
  LIVEKIT_URL         wss://your-project.livekit.cloud
  LIVEKIT_API_KEY
  LIVEKIT_API_SECRET
"""
import os
import time

import httpx
from jose import jwt


def config() -> tuple[str, str, str] | None:
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    return (url, key, secret) if url and key and secret else None


def make_token(*, room: str, identity: str, name: str, publish: bool, ttl_seconds: int = 4 * 3600) -> str:
    cfg = config()
    assert cfg is not None
    _, key, secret = cfg
    now = int(time.time())
    claims = {
        "iss": key,
        "sub": identity,
        "name": name,
        "nbf": now - 10,
        "exp": now + ttl_seconds,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": publish,
            "canPublishData": publish,
            "canSubscribe": True,
        },
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def close_room(room: str) -> None:
    """Best effort: when the host ends the stream, also drop everyone still connected to the room. Failing here is harmless (viewers
    find out from the chat poll that the stream ended), so nothing is raised."""
    cfg = config()
    if cfg is None:
        return
    url, key, secret = cfg
    http = url.replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")
    now = int(time.time())
    admin = jwt.encode(
        {"iss": key, "sub": "server", "nbf": now - 10, "exp": now + 60, "video": {"roomCreate": True, "room": room}},
        secret,
        algorithm="HS256",
    )
    try:
        httpx.post(
            f"{http}/twirp/livekit.RoomService/DeleteRoom",
            json={"room": room},
            headers={"Authorization": f"Bearer {admin}"},
            timeout=5,
        )
    except Exception:
        pass


def remove_participant(room: str, identity: str) -> None:
    """Best effort: drops one person from the room (the host blocked them). Failing is harmless: they cannot get a new token, and
    the chat poll tells their screen to leave."""
    cfg = config()
    if cfg is None:
        return
    url, key, secret = cfg
    http = url.replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")
    now = int(time.time())
    admin = jwt.encode(
        {"iss": key, "sub": "server", "nbf": now - 10, "exp": now + 60, "video": {"roomAdmin": True, "room": room}},
        secret,
        algorithm="HS256",
    )
    try:
        httpx.post(
            f"{http}/twirp/livekit.RoomService/RemoveParticipant",
            json={"room": room, "identity": identity},
            headers={"Authorization": f"Bearer {admin}"},
            timeout=5,
        )
    except Exception:
        pass


def recording_enabled() -> bool:
    """Recording needs LiveKit's egress service AND our R2 storage settings; LIVE_RECORDING=0 turns it off."""
    return os.environ.get("LIVE_RECORDING", "1") != "0" and all(
        os.environ.get(k) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL")
    )


def _admin_headers(grant: dict) -> dict[str, str]:
    cfg = config()
    assert cfg is not None
    _, key, secret = cfg
    now = int(time.time())
    token = jwt.encode({"iss": key, "sub": "server", "nbf": now - 10, "exp": now + 60, "video": grant}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _http_url() -> str:
    cfg = config()
    assert cfg is not None
    return cfg[0].replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")


def replay_key(stream_id) -> str:
    return f"live/{stream_id}.mp4"


def replay_url(stream_id) -> str:
    return f"{os.environ['R2_PUBLIC_BASE_URL'].rstrip('/')}/{replay_key(stream_id)}"


def start_recording(room: str, stream_id) -> str | None:
    """Ask LiveKit to record the room to an mp4 in our R2 bucket (key live/<stream id>.mp4). Returns the egress id, or None when it
    could not start — a live without a recording is still a live, so this never raises."""
    if config() is None or not recording_enabled():
        return None
    try:
        r = httpx.post(
            f"{_http_url()}/twirp/livekit.Egress/StartRoomCompositeEgress",
            json={
                "roomName": room,
                # Phone-shaped (portrait) recording that the host's picture fills, so it fills a phone screen on replay. The
                # default is a wide 16:9 frame, which leaves a portrait video as a small strip in the middle.
                "layout": "single-speaker",
                "advanced": {"width": 1080, "height": 1920, "depth": 24, "framerate": 30, "videoBitrate": 6000},
                "fileOutputs": [
                    {
                        "fileType": "MP4",
                        "filepath": replay_key(stream_id),
                        "s3": {
                            "accessKey": os.environ["R2_ACCESS_KEY_ID"],
                            "secret": os.environ["R2_SECRET_ACCESS_KEY"],
                            "region": "auto",
                            "endpoint": f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                            "bucket": os.environ["R2_BUCKET_NAME"],
                            "forcePathStyle": True,
                        },
                    }
                ],
            },
            headers=_admin_headers({"roomRecord": True}),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("egressId") or r.json().get("egress_id")
    except Exception:
        return None


def stop_recording(egress_id: str) -> None:
    """Best effort: closing the room finishes the recording anyway; this just does it promptly."""
    if config() is None:
        return
    try:
        httpx.post(
            f"{_http_url()}/twirp/livekit.Egress/StopEgress",
            json={"egressId": egress_id},
            headers=_admin_headers({"roomRecord": True}),
            timeout=5,
        )
    except Exception:
        pass
