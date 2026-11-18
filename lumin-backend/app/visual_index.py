"""Look-alike products for a picture ("find similar" on the Found it screen).

Every product's first photo is turned into a small vector and kept in product_visuals. A picture someone scans is turned
into the same kind of vector and the closest products are listed.

Two kinds of vector, never mixed:
  "model1"   from a picture model (the same optional ONNX model as app/scan_embed.py: SCAN_EMBED_MODEL). Understands what
             the item IS (a trainer, a handbag), not only its colours. Use this one for real quality.
  "colour1"  built in, needs nothing installed: colour mix, where the colours sit, and the direction of edges. Finds
             items that LOOK alike (same colours and rough shape); it does not know what the item is. Honest, but weaker.

The index fills itself: the worker describes a few products whenever it is idle (jobs.py), and
  python -m app.visual_index --backfill        does the lot in one go (run it once after deploying).
"""
import logging
import os
import sys
import tempfile
import threading
import time
import uuid

import cv2
import numpy as np
from sqlalchemy.orm import Session, joinedload

from app import scan_embed, storage
from app.database import SessionLocal
from app.models import Product, ProductVisual

log = logging.getLogger("lumin")

KIND_COLOUR = "colour1"
KIND_MODEL = "model1"
MIN_SIM = {KIND_COLOUR: 0.80, KIND_MODEL: 0.55}  # below this a product is not "similar" (the colour one is uncalibrated)
RESULTS = 12
CACHE_S = 300.0

_LOCK = threading.Lock()
_CACHE: dict = {"kind": None, "at": 0.0, "ids": [], "mat": None}


def active_kind() -> str:
    return KIND_MODEL if scan_embed.enabled() else KIND_COLOUR


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


def colour_descriptor(bgr: np.ndarray) -> np.ndarray:
    """Unit vector: colour mix + where the colours sit + edge directions. Looks at the middle of the picture (where the
    item usually is); the exact same picture always gives the exact same vector."""
    h, w = bgr.shape[:2]
    bgr = bgr[int(h * 0.1) : int(h * 0.9), int(w * 0.1) : int(w * 0.9)]
    im = cv2.resize(bgr, (96, 96), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 3, 3], [0, 180, 0, 256, 0, 256]).flatten()
    hist = _unit(np.sqrt(hist / (hist.sum() + 1e-9)))
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32) / 255.0
    layout = _unit((cv2.resize(lab, (3, 3), interpolation=cv2.INTER_AREA) - 0.5).flatten())
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag, ang = cv2.cartToPolar(gx, gy)
    bins = (ang / (2 * np.pi) * 8).astype(int) % 8
    edges = np.zeros((2, 2, 8), np.float32)
    for r in range(2):
        for c in range(2):
            b = bins[r * 48 : (r + 1) * 48, c * 48 : (c + 1) * 48].ravel()
            m = mag[r * 48 : (r + 1) * 48, c * 48 : (c + 1) * 48].ravel()
            edges[r, c] = np.bincount(b, weights=m, minlength=8)
    edge = _unit(np.sqrt(edges.flatten() / (edges.sum() + 1e-9)))
    return _unit(np.concatenate([0.6 * hist, 0.5 * layout, 0.3 * edge]).astype(np.float32))


def describe(bgr: np.ndarray) -> tuple[str, np.ndarray] | None:
    """(kind, unit vector) for a colour picture, or None when it can't be read."""
    if bgr is None or bgr.size == 0 or min(bgr.shape[:2]) < 16:
        return None
    if scan_embed.enabled():
        v = scan_embed.embed_color([bgr])
        if v is not None:
            return KIND_MODEL, v[0]
    return KIND_COLOUR, colour_descriptor(bgr)


def _decode(data: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def _first_photo(p: Product) -> str | None:
    imgs = sorted(p.images, key=lambda i: i.position)
    return imgs[0].url if imgs else None


def _index_product(db: Session, p: Product) -> bool:
    url = _first_photo(p)
    key = storage.key_from_view_url(url)
    if not url or key is None:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "photo")
            storage.download_object(key, path)
            with open(path, "rb") as f:
                d = describe(_decode(f.read()))
    except Exception:
        log.warning("visual index: could not read the photo of product %s", p.id, exc_info=True)
        d = None
    if d is None:
        return False
    kind, vec = d
    row = db.get(ProductVisual, p.id)
    blob = vec.astype(np.float16).tobytes()
    if row is None:
        db.add(ProductVisual(product_id=p.id, image_url=url, kind=kind, vec=blob))
    else:
        row.image_url, row.kind, row.vec = url, kind, blob
    db.commit()
    return True


_TRIED_IDS: set = set()  # a product whose photo can't be read is tried once per process, so it can't loop


def index_some(limit: int = 3) -> bool:
    """Describe up to `limit` products that have no vector yet (or one made another way, e.g. before a picture model was
    switched on). -> True when it did some work. Called by the job loop when idle. A product whose first photo is replaced
    later keeps its old vector until it is rebuilt with --backfill (after deleting its row)."""
    db = SessionLocal()
    try:
        kind = active_kind()
        have = db.query(ProductVisual.product_id).filter(ProductVisual.kind == kind)
        q = (
            db.query(Product)
            .options(joinedload(Product.images))
            .filter(Product.id.notin_(have), Product.images.any())
            .order_by(Product.created_at.desc())
            .limit(limit + len(_TRIED_IDS))
        )
        n = tried = 0
        for p in q.all():
            if tried >= limit:
                break
            if p.id in _TRIED_IDS:
                continue
            _TRIED_IDS.add(p.id)
            tried += 1
            if _index_product(db, p):
                n += 1
        if n:
            _CACHE["at"] = 0.0  # the next lookup reloads
        return tried > 0
    except Exception:
        log.exception("visual index failed")
        db.rollback()
        return False
    finally:
        db.close()


def _load(db: Session, kind: str):
    now = time.monotonic()
    with _LOCK:
        if _CACHE["kind"] == kind and _CACHE["mat"] is not None and now - _CACHE["at"] < CACHE_S:
            return _CACHE["ids"], _CACHE["mat"]
    rows = db.query(ProductVisual.product_id, ProductVisual.vec).filter(ProductVisual.kind == kind).all()
    ids = [r[0] for r in rows]
    mat = np.stack([np.frombuffer(r[1], np.float16).astype(np.float32) for r in rows]) if rows else None
    with _LOCK:
        _CACHE.update(kind=kind, at=now, ids=ids, mat=mat)
    return ids, mat


def similar_ids(db: Session, bgr: np.ndarray, exclude: set | None = None, limit: int = RESULTS) -> tuple[str, list[tuple[uuid.UUID, float]]]:
    """-> (kind, [(product id, similarity)] best first). Empty when nothing is close enough or nothing is indexed yet."""
    kind = active_kind()
    d = describe(bgr)
    if d is None or d[0] != kind:
        return kind, []
    ids, mat = _load(db, kind)
    if mat is None:
        return kind, []
    sims = mat @ d[1]
    out: list[tuple[uuid.UUID, float]] = []
    for i in np.argsort(-sims)[: limit * 4]:
        if sims[i] < MIN_SIM[kind]:
            break
        if exclude and ids[i] in exclude:
            continue
        out.append((ids[i], float(sims[i])))
        if len(out) >= limit:
            break
    return kind, out


def backfill() -> int:
    total = 0
    while index_some(50):
        total += 50
        print(f"described {total}+ products", flush=True)
    return total


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        backfill()
        print("done")
    else:
        print(__doc__)
