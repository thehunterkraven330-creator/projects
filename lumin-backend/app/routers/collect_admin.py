"""Admin: collect-in-person orders, how each ended and why, and which sellers keep being turned down or not turning up."""
import uuid
from datetime import datetime

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import order_cancel
from app.auth import get_current_admin
from app.database import get_db
from app.models import CollectNoShow, MerchantAccount, Order, OrderStatus
from app.models.collect import NOSHOW_CLAIMED, NOSHOW_CONFIRMED, NOSHOW_DISMISSED, NOSHOW_DISPUTED

router = APIRouter(prefix="/admin/collect", tags=["admin-collect"], dependencies=[Depends(get_current_admin)])


class CollectOrderRow(BaseModel):
    order_id: uuid.UUID
    product_name: str | None = None
    buyer_name: str | None = None
    seller_name: str | None = None
    seller_id: uuid.UUID | None = None
    status: str
    outcome: str  # waiting | accepted | rejected | seller_not_there | seller_refused | not_collected | cancelled
    reason: str | None = None
    created_at: datetime
    deadline: datetime | None = None


class CollectSellerRow(BaseModel):
    seller_id: uuid.UUID
    seller_name: str | None = None
    accepted: int
    rejected: int
    seller_not_there: int
    seller_refused: int
    not_collected: int
    no_show_strikes: int  # confirmed by an admin, of either kind


class NoShowRow(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_name: str | None = None
    seller_id: uuid.UUID
    seller_name: str | None = None
    buyer_name: str | None = None
    kind: str = "not_there"
    status: str
    planned_for: datetime | None = None
    buyer_note: str | None = None
    buyer_photo_url: str
    seller_note: str | None = None
    seller_photo_url: str | None = None
    seller_replied: bool
    created_at: datetime


class CollectOverview(BaseModel):
    orders: list[CollectOrderRow]
    sellers: list[CollectSellerRow]
    noshows: list[NoShowRow] = []


def outcome_of(order: Order) -> str:
    """How a collect order stands, read from its status and cancel reason (see order_cancel's prefixes)."""
    if order.status == OrderStatus.delivered:
        return "accepted"
    if order.status != OrderStatus.cancelled:
        return "waiting"
    reason = order.cancel_reason or ""
    if reason.startswith(order_cancel.NO_SHOW_PREFIX):
        return "seller_not_there"
    if reason.startswith(order_cancel.REFUSED_PREFIX):
        return "seller_refused"
    if reason.startswith(order_cancel.REJECT_PREFIX):
        return "rejected"
    if reason.startswith("Cancelled: the item was not collected"):
        return "not_collected"
    return "cancelled"


@router.get("", response_model=CollectOverview)
def collect_overview(db: Session = Depends(get_db)):
    orders = (
        db.query(Order)
        .filter(Order.collect_in_person.is_(True))
        .order_by(Order.created_at.desc())
        .limit(500)
        .all()
    )
    rows: list[CollectOrderRow] = []
    per_seller: dict[uuid.UUID, CollectSellerRow] = {}
    for o in orders:
        merchant = o.product.merchant if o.product is not None else None
        out = outcome_of(o)
        reason = o.cancel_reason
        for prefix in (order_cancel.NO_SHOW_PREFIX, order_cancel.REFUSED_PREFIX, order_cancel.REJECT_PREFIX):
            if reason and reason.startswith(prefix):
                reason = reason[len(prefix):]
        rows.append(CollectOrderRow(
            order_id=o.id, product_name=o.product_name, buyer_name=o.buyer_name,
            seller_name=merchant.business_name if merchant else None, seller_id=merchant.id if merchant else None,
            status=o.status.value, outcome=out, reason=reason if out in ("rejected", "seller_not_there", "seller_refused") else None,
            created_at=o.created_at, deadline=o.collect_deadline,
        ))
        if merchant is not None:
            s = per_seller.setdefault(merchant.id, CollectSellerRow(
                seller_id=merchant.id, seller_name=merchant.business_name, accepted=0, rejected=0, seller_not_there=0,
                seller_refused=0, not_collected=0, no_show_strikes=merchant.collect_no_show_strikes or 0,
            ))
            if out in ("accepted", "rejected", "seller_not_there", "seller_refused", "not_collected"):
                setattr(s, out, getattr(s, out) + 1)
    sellers = sorted(per_seller.values(), key=lambda s: (s.rejected + s.seller_not_there + s.seller_refused), reverse=True)
    noshows = []
    for c in db.query(CollectNoShow).order_by(CollectNoShow.created_at.desc()).limit(200).all():
        order = db.get(Order, c.order_id)
        merchant = db.get(MerchantAccount, c.merchant_id)
        noshows.append(NoShowRow(
            id=c.id, order_id=c.order_id, product_name=order.product_name if order else None, seller_id=c.merchant_id,
            seller_name=merchant.business_name if merchant else None, buyer_name=order.buyer_name if order else None, kind=c.kind, status=c.status,
            planned_for=c.planned_for, buyer_note=c.note, buyer_photo_url=c.photo_url, seller_note=c.seller_note,
            seller_photo_url=c.seller_photo_url, seller_replied=c.seller_replied_at is not None, created_at=c.created_at,
        ))
    return CollectOverview(orders=rows, sellers=sellers, noshows=noshows)


def _decide(db: Session, claim_id: uuid.UUID, status: str) -> None:
    from datetime import datetime as _dt

    claim = db.query(CollectNoShow).filter(CollectNoShow.id == claim_id).with_for_update().one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status not in (NOSHOW_CLAIMED, NOSHOW_DISPUTED):
        db.rollback()
        raise HTTPException(status_code=409, detail="This claim has already been decided.")
    claim.status = status
    claim.resolved_at = _dt.now(timezone.utc)
    if status == NOSHOW_CONFIRMED:
        merchant = db.get(MerchantAccount, claim.merchant_id)
        if merchant is not None:
            merchant.collect_no_show_strikes = (merchant.collect_no_show_strikes or 0) + 1
    db.commit()


@router.post("/noshows/{claim_id}/confirm", response_model=dict[str, bool])
def confirm_noshow(claim_id: uuid.UUID, db: Session = Depends(get_db)):
    """The admin agrees the seller was not there: the seller gets a strike."""
    _decide(db, claim_id, NOSHOW_CONFIRMED)
    return {"ok": True}


@router.post("/noshows/{claim_id}/dismiss", response_model=dict[str, bool])
def dismiss_noshow(claim_id: uuid.UUID, db: Session = Depends(get_db)):
    """The admin does not agree: no strike."""
    _decide(db, claim_id, NOSHOW_DISMISSED)
    return {"ok": True}
