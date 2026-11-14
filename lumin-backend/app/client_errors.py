"""Errors that happen in the browser or the phone app (website and admin panel), sent here so they show up in the Railway log
and, when SENTRY_DSN is set, in Sentry. Without this a screen that crashes on someone's phone is invisible unless they tell you.

Kept free of FastAPI so the cleaning rules can be tested on their own. What is kept: the message, a short stack, the page path (no
query string, no #fragment), and a few tags. What is never kept: tokens, e-mail addresses, the query string, cookies or any user id.
"""
import re

MAX_MESSAGE = 500
MAX_STACK = 4000

_JWT = re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]{8,}")
_SECRET_PARAM = re.compile(r"(?i)\b(token|access_token|refresh_token|key|secret|password|code)=([^&\s\"']+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrub(text: "str | None", limit: int) -> str:
    """Remove anything that looks like a credential or an address, flatten line breaks in the log line sense is left to the caller,
    and cut to `limit` characters."""
    if not text:
        return ""
    t = str(text)[: limit * 2]
    t = _JWT.sub("[token]", t)
    t = _BEARER.sub("Bearer [token]", t)
    t = _SECRET_PARAM.sub(lambda m: f"{m.group(1)}=[removed]", t)
    t = _EMAIL.sub("[email]", t)
    return t[:limit]


def clean_path(path: "str | None") -> str:
    """The page the error happened on: path only. '/v/123?token=x#y' -> '/v/123'. Anything that is not a path is dropped."""
    if not path:
        return ""
    p = str(path).split("#", 1)[0].split("?", 1)[0][:200]
    return p if p.startswith("/") else ""


def one_line(text: str) -> str:
    """Flatten line breaks so a message can never fake a second log line."""
    return re.sub(r"[\r\n\t]+", " | ", text)
