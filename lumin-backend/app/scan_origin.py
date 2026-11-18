"""Who a scan came from, for the public search count (app/models/scan.py).

A small middleware notes the browser/phone id the app sends (X-Device-Id) and a one-way hash of the network address for the
current request; the VideoScan row picks them up when it is saved, so none of the places that record a scan has to pass them on.
The address is stored only as a salted hash and only to cap how many signed-out searches one network can add."""
import hashlib
import os
import re
from contextvars import ContextVar

from fastapi import FastAPI, Request

_DEVICE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SALT = os.environ.get("SCAN_IP_SALT") or os.environ.get("SECRET_KEY", "lumin")

# (device id or None, hashed network address or None) for the request being handled
current: ContextVar[tuple[str | None, str | None]] = ContextVar("scan_origin", default=(None, None))


def client_ip(request: Request) -> str | None:
    # Behind the host's proxy the real client is the LAST address it appended; earlier ones can be made up by the caller.
    fwd = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in fwd.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return request.client.host if request.client else None


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def note_scan_origin(request: Request, call_next):
        if request.url.path.startswith("/scan"):
            device = request.headers.get("x-device-id", "")
            ip = client_ip(request)
            ip_hash = hashlib.sha256(f"{_SALT}:{ip}".encode()).hexdigest()[:40] if ip else None
            token = current.set((device if _DEVICE.match(device) else None, ip_hash))
            try:
                return await call_next(request)
            finally:
                current.reset(token)
        return await call_next(request)
