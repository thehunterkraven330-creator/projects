import logging
from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.client_errors import MAX_MESSAGE, MAX_STACK, clean_path, one_line, scrub
from app.rate_limit import limiter

log = logging.getLogger("lumin")

router = APIRouter(prefix="/client-errors", tags=["client-errors"])


class ClientError(BaseModel):
    source: Literal["web", "admin"]
    message: str = Field(min_length=1, max_length=2000)
    stack: str | None = Field(default=None, max_length=12000)
    path: str | None = Field(default=None, max_length=400)
    kind: Literal["error", "rejection", "render"] = "error"


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
def record_client_error(request: Request, payload: ClientError):
    """No sign-in needed (an app that crashes before login still has to be able to say so), so it is rate limited and everything in
    it is cleaned before use. It writes one warning line to the log and, when Sentry is on, one event. It stores nothing."""
    message = scrub(payload.message, MAX_MESSAGE)
    stack = scrub(payload.stack, MAX_STACK)
    path = clean_path(payload.path)
    log.warning("client error [%s/%s] %s | page=%s | %s", payload.source, payload.kind, one_line(message), path or "?", one_line(stack)[:300])
    try:
        import sentry_sdk

        sentry_sdk.capture_event(
            {
                "message": message,
                "level": "error",
                "logger": f"client.{payload.source}",
                "tags": {"source": payload.source, "kind": payload.kind},
                "extra": {"page": path, "stack": stack},
                "fingerprint": [payload.source, payload.kind, message[:120]],
            }
        )
    except Exception:  # Sentry missing or not set up: the log line above is enough
        pass
