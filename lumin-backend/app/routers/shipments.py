"""Delivery of sealed orders: the buyer's check at the door (/orders/{id}/delivery), the courier's calls (/courier) and the
admin's manual courier console (/admin/shipments). Rules live in app/shipments.py; the courier behind it in app/courier.py."""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import courier, seals, shipments
from app.auth import get_current_active_user, get_current_admin
from app.database import get_db
from app.models import MerchantAccount, Order, Product, SealBag, Shipment, User
from app.rate_limit import limiter

router = APIRouter(tags=["shipments"])
courier_router = APIRouter(prefix="/courier", tags=["courier"])
admin_router = APIRouter(prefix="/admin/shipments", tags=["admin-shipments"], dependencies=[Depends(get_current_admin)])


def _raise(e: seals.SealError):
    raise HTTPException(status_code=e.status, detail=str(e))


class ShipmentRead(BaseModel):
    order_id: uuid.UUID
    serial: str | None
    status: str
    courier: str
    driver_name: str | None = None
    picked_up_at: datetime | None = None
    arrived_at: datetime | None = None
    seal_intact: bool | None = None
    delivered_at: datetime | None = None


def _read(db: Session, s: Shipment) -> ShipmentRead:
    bag = db.get(SealBag, s.bag_id) if s.bag_id else None
    return ShipmentRead(
        order_id=s.order_id, serial=bag.serial if bag else None, status=s.status, courier=s.courier,
        driver_name=s.driver_name, picked_up_at=s.picked_up_at, arrived_at=s.arrived_at, seal_intact=s.seal_intact,
        delivered_at=s.delivered_at,
    )


# ------------------------------------------------------------------ buyer / seller
@router.get("/orders/{order_id}/delivery", response_model=ShipmentRead | None)
def order_delivery(order_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Where a sealed order is. The buyer or the selling merchant can ask; null when the order has no sealed bag."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    is_buyer = order.buyer_id == current_user.id
    is_seller = (
        current_user.merchant_account is not None
        and order.product is not None
        and order.product.merchant_id == current_user.merchant_account.id
    )
    if not is_buyer and not is_seller:
        raise HTTPException(status_code=404, detail="Order not found")
    s = shipments.get_for_order(db, order.id)
    return _read(db, s) if s else None


class SellerCourierStatus(BaseModel):
    tracked: bool
    ready: list[uuid.UUID]


@router.get("/shipments/seller-status", response_model=SellerCourierStatus)
def seller_courier_status(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """For the seller's orders list: is a courier connected, and which orders already have a driver requested (no sealed bag)."""
    rows = (
        db.query(Shipment.order_id)
        .join(Order, Order.id == Shipment.order_id)
        .join(Product, Product.id == Order.product_id)
        .join(MerchantAccount, MerchantAccount.id == Product.merchant_id)
        .filter(MerchantAccount.user_id == current_user.id, Shipment.bag_id.is_(None))
        .all()
    )
    return SellerCourierStatus(tracked=True, ready=[r[0] for r in rows])


@router.get("/shipments/mine", response_model=dict[str, str])
def my_shipments(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """order id -> shipment status, for the buyer's own orders that have a sealed bag (to show "scan the bag" when it arrives)."""
    rows = (
        db.query(Shipment.order_id, Shipment.status)
        .join(Order, Order.id == Shipment.order_id)
        .filter(Order.buyer_id == current_user.id, Shipment.bag_id.isnot(None))
        .all()
    )
    return {str(o): s for o, s in rows}


class ScanBody(BaseModel):
    code: str = Field(max_length=200)
    seal_intact: bool
    note: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=500)  # a photo of the opened bag (uploaded first), optional


class ScanResult(BaseModel):
    refused: bool
    otp: str | None = None
    expires_at: datetime | None = None


@router.post("/orders/{order_id}/delivery/scan", response_model=ScanResult)
@limiter.limit("10/minute")
def buyer_scan(
    request: Request,
    order_id: uuid.UUID,
    payload: ScanBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The buyer, at the door, with the bag in hand: scan its QR and say whether it is still sealed. Still sealed = a
    one-time 6-digit code to read to the driver. Opened = the delivery is refused and nothing is released."""
    try:
        return ScanResult(**shipments.buyer_scan(db, order_id, current_user, payload.code, payload.seal_intact, payload.note, payload.photo_url))
    except seals.SealError as e:
        _raise(e)


# ------------------------------------------------------------------ the courier's system
def _need_courier(key: str | None) -> None:
    if not courier.courier_key_ok(key):
        raise HTTPException(status_code=401, detail="Invalid courier key")


class AcceptBody(BaseModel):
    serial: str = Field(max_length=20)
    driver_name: str | None = Field(default=None, max_length=100)


class ConfirmBody(BaseModel):
    serial: str = Field(max_length=20)
    otp: str = Field(min_length=4, max_length=10)


@courier_router.post("/pickups/accept", response_model=ShipmentRead)
@limiter.limit("120/minute")
def courier_accept(request: Request, payload: AcceptBody, x_courier_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    """A driver accepted the job for this bag: it goes in transit. (A real courier calls this; the manual one uses the admin console.)"""
    _need_courier(x_courier_key)
    bag = db.query(SealBag).filter(SealBag.serial == payload.serial.strip().upper()).first()
    ship = db.query(Shipment).filter(Shipment.bag_id == bag.id).first() if bag else None
    if ship is None:
        raise HTTPException(status_code=404, detail="No shipment for that bag")
    try:
        return _read(db, shipments.mark_picked_up(db, ship.id, None, payload.driver_name))
    except seals.SealError as e:
        _raise(e)


@courier_router.post("/deliveries/confirm", response_model=ShipmentRead)
@limiter.limit("60/minute")
def courier_confirm(request: Request, payload: ConfirmBody, x_courier_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    """The driver typed the code the buyer read out: right = delivered, for ever."""
    _need_courier(x_courier_key)
    try:
        return _read(db, shipments.confirm_delivery(db, payload.serial, payload.otp))
    except seals.SealError as e:
        _raise(e)


@courier_router.post("/terminal-webhook")
@limiter.limit("300/minute")
async def terminal_webhook(request: Request, x_terminal_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Terminal Africa's status updates (register this URL as a webhook in their dashboard, https, with the shipment.* events).
    The signature is checked against the exact bytes received before anything is read."""
    import json

    from app import terminal

    raw = await request.body()
    if not os.environ.get("TERMINAL_AFRICA_SECRET_KEY"):
        raise HTTPException(status_code=503, detail="Not configured")
    if not terminal.verify_signature(raw, x_terminal_signature):
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"result": "ignored"}  # signed but not JSON: nothing to do, and no reason for Terminal to retry
    return {"result": shipments.handle_terminal_event(db, payload)}


# ------------------------------------------------------------------ admin (the manual courier)
class AdminShipmentRead(ShipmentRead):
    id: uuid.UUID
    refusal_note: str | None = None
    refusal_photo_url: str | None = None
    created_at: datetime
    product_name: str | None = None
    stalled: bool = False
    resolution: str | None = None
    loss_party: str | None = None
    # Where the driver collects it (the seller's saved pickup address); null if the seller has none.
    pickup_address: dict | None = None
    seller_name: str | None = None


@admin_router.get("", response_model=list[AdminShipmentRead])
def list_shipments(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Shipment)
    if status:
        q = q.filter(Shipment.status == status)
    out = []
    for s in q.order_by(Shipment.created_at.desc()).limit(200).all():
        order = db.get(Order, s.order_id)
        out.append(
            AdminShipmentRead(**_read(db, s).model_dump(), id=s.id, refusal_note=s.refusal_note, refusal_photo_url=s.refusal_photo_url,
                              created_at=s.created_at, product_name=order.product_name if order else None,
                              stalled=shipments.is_stalled(s), resolution=s.resolution, loss_party=s.loss_party,
                              pickup_address=(order.product.merchant.pickup_address if order and order.product and order.product.merchant else None),
                              seller_name=(order.product.merchant.business_name if order and order.product and order.product.merchant else None))
        )
    return out


class DriverBody(BaseModel):
    driver_name: str | None = Field(default=None, max_length=100)


@admin_router.post("/{shipment_id}/pickup", response_model=ShipmentRead)
def admin_pickup(shipment_id: uuid.UUID, payload: DriverBody, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Manual courier: a driver has collected the bag."""
    try:
        return _read(db, shipments.mark_picked_up(db, shipment_id, admin.id, payload.driver_name))
    except seals.SealError as e:
        _raise(e)


class OtpBody(BaseModel):
    otp: str = Field(min_length=4, max_length=10)


@admin_router.post("/{shipment_id}/confirm", response_model=ShipmentRead)
def admin_confirm(shipment_id: uuid.UUID, payload: OtpBody, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Manual courier: the driver read out the code the buyer gave them."""
    s = db.get(Shipment, shipment_id)
    bag = db.get(SealBag, s.bag_id) if s else None
    if bag is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    try:
        return _read(db, shipments.confirm_delivery(db, bag.serial, payload.otp, admin.id))
    except seals.SealError as e:
        _raise(e)


class StuckOrder(BaseModel):
    order_id: uuid.UUID
    product_name: str | None = None
    seller_name: str | None = None


@admin_router.get("/stuck-orders", response_model=list[StuckOrder])
def stuck_orders(db: Session = Depends(get_db)):
    """Orders marked shipped by a seller before that was taken away from sellers: nothing else can deliver them."""
    return [
        StuckOrder(order_id=o.id, product_name=o.product_name,
                   seller_name=o.product.merchant.business_name if o.product is not None and o.product.merchant is not None else None)
        for o in shipments.stuck_shipped_orders(db)
    ]


@admin_router.post("/orders/{order_id}/delivered", response_model=dict[str, bool])
def admin_deliver_stuck_order(order_id: uuid.UUID, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if not shipments.deliver_stuck_order(db, order_id):
        raise HTTPException(status_code=409, detail="That order isn't a shipped order without a shipment.")
    return {"delivered": True}


@admin_router.post("/{shipment_id}/delivered", response_model=ShipmentRead)
def admin_delivered(shipment_id: uuid.UUID, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Manual courier, order WITHOUT a sealed bag: the courier says it was delivered. Starts the buyer's claim window."""
    s = db.get(Shipment, shipment_id)
    if s is None or not shipments.mark_courier_delivered(db, s.id):
        raise HTTPException(status_code=409, detail="This shipment can't be marked delivered (it needs to be in transit, with no sealed bag).")
    db.refresh(s)
    return _read(db, s)


class ResolveBody(BaseModel):
    action: str = Field(pattern="^(refund|redeliver|lost)$")
    loss_party: str | None = Field(default=None, pattern="^(courier|seller|platform)$")
    note: str | None = Field(default=None, max_length=300)


@admin_router.post("/{shipment_id}/resolve", response_model=ShipmentRead)
def admin_resolve(shipment_id: uuid.UUID, payload: ResolveBody, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Settle a shipment that didn't reach the buyer: refund (refused, bag opened), redeliver (the refusal was wrong) or lost
    (never arrived: refund the buyer). loss_party only records who bears the cost."""
    try:
        return _read(db, shipments.resolve(db, shipment_id, payload.action, admin.id, payload.loss_party, payload.note))
    except seals.SealError as e:
        _raise(e)
