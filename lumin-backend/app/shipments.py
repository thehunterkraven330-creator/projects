"""A sealed order's journey and the delivery code. The rules (all enforced here):

  * a shipment starts when the seller seals the bag: awaiting_pickup;
  * the driver's pickup moves it to in_transit, the bag to in_transit and the order to "shipped";
  * at the door the buyer scans the bag's QR (only the buyer, only a bag that is in transit) and says whether it is still
    sealed. Untouched: the app shows a 6-digit code (valid 30 minutes, 5 wrong tries, a hash kept). Opened: the delivery
    is refused and nothing is released;
  * the buyer reads the code to the driver; the driver's system (or an admin) sends it with the bag's serial. A right code
    moves the bag to delivered (for ever: it can never be used again), the order to delivered and starts the claim window.
"""
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import courier, seals
from app.brand import APP_NAME
from app.models import Notification, NotificationType, Order, OrderStatus, SealBag, Shipment
from app.models.seal import (
    BAG_DELIVERED,
    BAG_IN_TRANSIT,
    BAG_VOID,
    SHIP_AWAITING,
    SHIP_CLOSED,
    SHIP_DELIVERED,
    SHIP_IN_TRANSIT,
    SHIP_LOST,
    SHIP_REFUSED,
)
from app.return_policy import CLAIM_WINDOW_HOURS

log = logging.getLogger(__name__)

OTP_VALID = timedelta(minutes=30)
OTP_MAX_TRIES = 5
OTP_MAX_ISSUES = 5


def _notify(db: Session, user_id: "uuid.UUID | None", body: str, order: "Order | None" = None, seller: bool = False) -> None:
    """seller=True: the notice is about the person's business account, so a tap opens the business Orders."""
    if user_id is not None:
        db.add(Notification(
            user_id=user_id, body=body, type=NotificationType.order,
            audience="seller" if seller else None,
            target_id=order.id if order is not None else None,
            actor_id=order.buyer_id if (seller and order is not None) else None,
        ))


def _seller_user_id(order: Order) -> "uuid.UUID | None":
    return order.product.merchant.user_id if order.product is not None and order.product.merchant is not None else None


def _otp_hash(shipment_id: uuid.UUID, otp: str) -> str:
    return hashlib.sha256(f"{shipment_id}:{otp}".encode()).hexdigest()


def create_for_seal(db: Session, order: Order, bag: SealBag) -> Shipment:
    """Called right after a live test is sealed: a shipment waiting for a driver, and the courier is asked."""
    ship = db.query(Shipment).filter(Shipment.order_id == order.id).first()
    if ship is not None:
        return ship
    c = courier.get_courier()
    ship = Shipment(order_id=order.id, bag_id=bag.id, courier=c.name, status=SHIP_AWAITING)
    db.add(ship)
    db.flush()
    try:
        from app.gateway import is_test_reference

        if order.payment is not None and is_test_reference(order.payment.reference):
            ship.courier_ref = None  # a test order: no real driver is booked for a made-up address
        else:
            ship.courier_ref = c.request_pickup(ship, order)
    except Exception:
        log.exception("courier pickup request failed for order %s", order.id)  # the shipment stays waiting; an admin can retry
    _notify(db, _seller_user_id(order), f"Order {str(order.id)[:8]} is sealed and waiting for a driver to collect it.", order, seller=True)
    db.commit()
    return ship


def create_for_order(db: Session, order: Order) -> Shipment:
    """An order WITHOUT a live test: the seller says it is packed. A shipment with no bag is made and the courier is asked for a driver.
    From here the courier's own events move the order (shipped on pickup, delivered when the courier delivers it): see
    handle_terminal_event. Safe to call twice (the second call returns the same shipment)."""
    ship = db.query(Shipment).filter(Shipment.order_id == order.id).first()
    if ship is not None:
        return ship
    c = courier.get_courier()
    ship = Shipment(order_id=order.id, bag_id=None, courier=c.name, status=SHIP_AWAITING)
    db.add(ship)
    db.flush()
    try:
        from app.gateway import is_test_reference

        if order.payment is not None and is_test_reference(order.payment.reference):
            ship.courier_ref = None
        else:
            ship.courier_ref = c.request_pickup(ship, order)
    except Exception:
        log.exception("courier pickup request failed for order %s", order.id)  # stays waiting; the seller can ask again
    _notify(db, order.buyer_id, "The seller has packed your order and a driver has been requested.")
    db.commit()
    return ship


def retry_pickup(db: Session, ship: Shipment, order: Order) -> Shipment:
    """The seller taps Ready for pickup again after the courier request failed (no courier_ref yet). Does nothing once a driver is booked."""
    if ship.status != SHIP_AWAITING or ship.courier_ref:
        return ship
    try:
        ship.courier_ref = courier.get_courier().request_pickup(ship, order)
    except Exception:
        log.exception("courier pickup retry failed for order %s", order.id)
    db.commit()
    return ship


def mark_courier_delivered(db: Session, shipment_id: uuid.UUID) -> bool:
    """A bagless shipment the courier reports delivered: the order is delivered and the claim window starts. -> True if it changed.
    Only for shipments with no sealed bag; a sealed one is delivered by the buyer's code instead."""
    ship = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().one_or_none()
    if ship is None or ship.bag_id is not None or ship.status != SHIP_IN_TRANSIT:
        db.rollback()
        return False
    order = db.get(Order, ship.order_id)
    now = datetime.now(timezone.utc)
    ship.status = SHIP_DELIVERED
    ship.delivered_at = now
    if order is not None and order.status == OrderStatus.shipped:
        order.status = OrderStatus.delivered
        if order.delivered_at is None:
            order.delivered_at = now
        _notify(db, order.buyer_id, f"Delivered. You have {CLAIM_WINDOW_HOURS} hours to report a problem, or tap \"It's what I ordered\" to pay the seller now.")
        _notify(db, _seller_user_id(order), f"Order {str(order.id)[:8]} was delivered. Payment is released after {CLAIM_WINDOW_HOURS} hours unless the buyer reports a problem.", order, seller=True)
    db.commit()
    return True


def stuck_shipped_orders(db: Session) -> list:
    """Orders a seller marked shipped (before sellers lost that button) that have no shipment, so no courier event can ever deliver them."""
    return (
        db.query(Order)
        .outerjoin(Shipment, Shipment.order_id == Order.id)
        .filter(Order.status == OrderStatus.shipped, Shipment.id.is_(None))
        .order_by(Order.created_at)
        .limit(200)
        .all()
    )


def deliver_stuck_order(db: Session, order_id: uuid.UUID) -> bool:
    """An admin confirms an order of that kind really arrived: a bagless shipment is recorded and delivered (claim window starts)."""
    order = db.query(Order).filter(Order.id == order_id).with_for_update().one_or_none()
    if order is None or order.status != OrderStatus.shipped or get_for_order(db, order.id) is not None:
        db.rollback()
        return False
    now = datetime.now(timezone.utc)
    db.add(Shipment(order_id=order.id, bag_id=None, courier=courier.get_courier().name, status=SHIP_IN_TRANSIT, picked_up_at=now))
    db.flush()
    ship = get_for_order(db, order.id)
    db.commit()
    return mark_courier_delivered(db, ship.id)


def get_for_order(db: Session, order_id: uuid.UUID) -> "Shipment | None":
    return db.query(Shipment).filter(Shipment.order_id == order_id).first()


def mark_picked_up(db: Session, shipment_id: uuid.UUID, actor_id: "uuid.UUID | None", driver_name: "str | None" = None) -> Shipment:
    ship = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().one_or_none()
    if ship is None:
        raise seals.SealError("not_found", "Shipment not found.", 404)
    if ship.status != SHIP_AWAITING:
        db.rollback()
        raise seals.SealError("bad_status", "This shipment isn't waiting for a driver.", 409)
    order = db.get(Order, ship.order_id)
    if ship.bag_id is not None:
        seals.advance(db, ship.bag_id, BAG_IN_TRANSIT, actor_id, "driver accepted", commit=False)
    ship.status = SHIP_IN_TRANSIT
    ship.picked_up_at = datetime.now(timezone.utc)
    ship.driver_name = (driver_name or None) and driver_name.strip()[:100]
    if order is not None and order.status == OrderStatus.pending:
        order.status = OrderStatus.shipped
    if order is not None:
        _notify(
            db,
            order.buyer_id,
            "Your order is on its way. When it arrives, check the bag is still sealed and scan its QR code."
            if ship.bag_id is not None
            else "Your order is on its way.",
        )
        _notify(db, _seller_user_id(order), f"A driver collected order {str(order.id)[:8]}. It's in transit.", order, seller=True)
    db.commit()
    return ship


def buyer_scan(db: Session, order_id: uuid.UUID, buyer, raw_code: str, seal_intact: bool, note: "str | None", photo_url: "str | None" = None) -> dict:
    """The buyer's check at the door. -> {"refused": bool, "otp": str | None, "expires_at": datetime | None}."""
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != buyer.id:
        raise seals.SealError("not_found", "Order not found.", 404)
    ship = db.query(Shipment).filter(Shipment.order_id == order.id).with_for_update().one_or_none()
    if ship is None or ship.status != SHIP_IN_TRANSIT:
        db.rollback()
        raise seals.SealError("not_in_transit", "This order isn't out for delivery yet.", 409)
    bag = seals.find_bag(db, raw_code)
    if bag is None or bag.id != ship.bag_id:
        db.rollback()
        raise seals.SealError("wrong_bag", "That QR code isn't on this order's bag.", 400)
    now = datetime.now(timezone.utc)
    ship.arrived_at = ship.arrived_at or now
    ship.seal_intact = bool(seal_intact)
    if not seal_intact:
        ship.status = SHIP_REFUSED
        ship.otp_hash = None
        ship.refusal_note = (note or None) and note.strip()[:500]
        ship.refusal_photo_url = (photo_url or None) and photo_url[:500]
        _notify(db, _seller_user_id(order), f"The buyer refused order {str(order.id)[:8]} at the door: the bag looked opened. {APP_NAME} will review it.", order, seller=True)
        db.commit()
        return {"refused": True, "otp": None, "expires_at": None}
    if ship.otp_issued >= OTP_MAX_ISSUES:
        db.rollback()
        raise seals.SealError("too_many_codes", "Too many delivery codes were requested. Contact support.", 429)
    otp = f"{secrets.randbelow(1_000_000):06d}"
    ship.otp_hash = _otp_hash(ship.id, otp)
    ship.otp_expires_at = now + OTP_VALID
    ship.otp_attempts = 0
    ship.otp_issued += 1
    db.commit()
    return {"refused": False, "otp": otp, "expires_at": ship.otp_expires_at}


def confirm_delivery(db: Session, serial: str, otp: str, actor_id: "uuid.UUID | None" = None) -> Shipment:
    """The driver's side: the bag's serial and the code the buyer read out. Right code = delivered."""
    bag = db.query(SealBag).filter(SealBag.serial == (serial or "").strip().upper()).first()
    ship = db.query(Shipment).filter(Shipment.bag_id == bag.id).with_for_update().one_or_none() if bag else None
    if ship is None:
        db.rollback()
        raise seals.SealError("not_found", "No shipment for that bag.", 404)
    if ship.status != SHIP_IN_TRANSIT or not ship.otp_hash:
        db.rollback()
        raise seals.SealError("no_code", "The buyer hasn't scanned the bag at the door yet.", 409)
    now = datetime.now(timezone.utc)
    if ship.otp_expires_at is None or now > ship.otp_expires_at:
        db.rollback()
        raise seals.SealError("code_expired", "That delivery code has expired. The buyer must scan the bag again.", 410)
    if ship.otp_attempts >= OTP_MAX_TRIES:
        db.rollback()
        raise seals.SealError("locked", "Too many wrong codes. The buyer must scan the bag again for a new one.", 423)
    ship.otp_attempts += 1
    if not hmac.compare_digest(ship.otp_hash, _otp_hash(ship.id, (otp or "").strip())):
        db.commit()  # the wrong try is counted even though this fails
        left = OTP_MAX_TRIES - ship.otp_attempts
        raise seals.SealError("wrong_code", f"That code isn't right. {left} {'try' if left == 1 else 'tries'} left.", 400)
    order = db.get(Order, ship.order_id)
    seals.advance(db, ship.bag_id, BAG_DELIVERED, actor_id, "delivery code confirmed", commit=False)
    ship.status = SHIP_DELIVERED
    ship.delivered_at = now
    ship.otp_hash = None
    if order is not None:
        order.status = OrderStatus.delivered
        if order.delivered_at is None:
            order.delivered_at = now  # starts the claim window
        _notify(
            db,
            order.buyer_id,
            f"Delivered. You have {CLAIM_WINDOW_HOURS} hours to report a problem, or tap \"It's what I ordered\" to pay the seller now.",
        )
        _notify(db, _seller_user_id(order), f"Order {str(order.id)[:8]} was delivered. Payment is released after {CLAIM_WINDOW_HOURS} hours unless the buyer reports a problem.", order, seller=True)
    db.commit()
    return ship


# ------------------------------------------------------------------ refused / lost: settled by an admin
RESOLUTIONS = {"refund", "redeliver", "lost"}
LOSS_PARTIES = {"courier", "seller", "platform"}


def resolve(db: Session, shipment_id: uuid.UUID, action: str, admin_id: uuid.UUID, loss_party: "str | None", note: "str | None") -> Shipment:
    """An admin settles a shipment that did not reach the buyer.
      refund    - the buyer refused an opened bag: refund the buyer, void the bag, cancel the order;
      redeliver - the refusal was a mistake or the bag was fine: the shipment goes back to in transit (the buyer scans again);
      lost      - an in-transit package never arrived: refund the buyer, void the bag, cancel the order.
    loss_party (courier / seller / platform) only records who bears the cost, for the books."""
    from fastapi import HTTPException

    from app.escrow import refund_for_defect

    if action not in RESOLUTIONS:
        raise seals.SealError("bad_action", "Unknown action.")
    if loss_party is not None and loss_party not in LOSS_PARTIES:
        raise seals.SealError("bad_party", "Unknown party.")
    ship = db.query(Shipment).filter(Shipment.id == shipment_id).with_for_update().one_or_none()
    if ship is None:
        raise seals.SealError("not_found", "Shipment not found.", 404)
    order = db.get(Order, ship.order_id)
    now = datetime.now(timezone.utc)
    if action == "redeliver":
        if ship.status != SHIP_REFUSED:
            db.rollback()
            raise seals.SealError("bad_status", "Only a refused shipment can be sent out again.", 409)
        ship.status = SHIP_IN_TRANSIT
        ship.seal_intact = None
        ship.arrived_at = None
        ship.otp_hash = None
        ship.resolution = "redeliver"
        ship.resolved_at = now
        if order is not None:
            _notify(db, order.buyer_id, f"{APP_NAME} reviewed your refused delivery and is sending it out again. Check the bag when it arrives.")
        db.commit()
        return ship
    allowed = SHIP_REFUSED if action == "refund" else SHIP_IN_TRANSIT
    if ship.status != allowed:
        db.rollback()
        raise seals.SealError("bad_status", "That action doesn't fit this shipment's status.", 409)
    if order is None:
        db.rollback()
        raise seals.SealError("not_found", "Order not found.", 404)
    try:
        refund_for_defect(db, order)  # a full refund of this order's own price (only while the funds are still held)
    except HTTPException as e:
        db.rollback()
        raise seals.SealError("refund_failed", str(e.detail), 409)
    order.status = OrderStatus.cancelled
    order.cancel_reason = "Delivery refused: bag opened" if action == "refund" else "Lost in transit"
    if ship.bag_id is not None:
        seals.advance(db, ship.bag_id, BAG_VOID, admin_id, f"{action}: {note or 'settled by admin'}", commit=False)
    ship.status = SHIP_LOST if action == "lost" else SHIP_CLOSED
    ship.resolution = "lost" if action == "lost" else "refund"
    ship.loss_party = loss_party
    ship.resolved_at = now
    msg = "Your order was refunded because the package was lost on the way." if action == "lost" else "Your refused delivery was reviewed and you have been refunded."
    _notify(db, order.buyer_id, msg)
    _notify(db, _seller_user_id(order), f"Order {str(order.id)[:8]} was refunded to the buyer ({'lost in transit' if action == 'lost' else 'bag arrived opened'}).", order, seller=True)
    db.commit()
    return ship


def on_order_cancelled(db: Session, order: Order) -> None:
    """Called before a seller/buyer cancels an order that has a sealed bag. Waiting for a driver: the bag is voided and the shipment
    closed. Already with a driver: cancelling isn't allowed (the buyer refuses at the door, or an admin settles it)."""
    ship = get_for_order(db, order.id)
    if ship is None:
        return
    if ship.status == SHIP_IN_TRANSIT:
        raise seals.SealError(
            "in_transit",
            "This order is with the driver. Refuse it at the door if the bag looks opened, or contact support."
            if ship.bag_id is not None
            else "This order is with the courier already. Contact support if it needs to be stopped.",
            409,
        )
    if ship.status == SHIP_AWAITING:
        if ship.bag_id is not None:
            seals.advance(db, ship.bag_id, BAG_VOID, None, "order cancelled before pickup", commit=False)
        ship.status = SHIP_CLOSED
        ship.resolution = "cancelled"
        ship.resolved_at = datetime.now(timezone.utc)
        _cancel_at_courier(ship)


def _cancel_at_courier(ship: Shipment) -> None:
    """Tell the courier not to send a driver. Never blocks the cancellation: the buyer's refund must not wait on a courier outage,
    so a failure is only logged (look for 'NOT cancelled at Terminal' and cancel it by hand in their dashboard)."""
    if ship.courier != "terminal" or not ship.courier_ref:
        return
    from app import terminal

    try:
        terminal.cancel(ship.courier_ref)
    except terminal.TerminalError as exc:
        log.error("Terminal shipment %s (order %s) was NOT cancelled at Terminal and a driver may still come: %s", ship.courier_ref, ship.order_id, exc)


# ------------------------------------------------------------------ reminders
PICKUP_REMIND_AFTER = timedelta(hours=24)
ARRIVAL_REMIND_AFTER = timedelta(hours=72)


def is_stalled(s: Shipment, now: "datetime | None" = None) -> bool:
    """Waiting for a driver for over a day, or on the road for over three days without the buyer scanning."""
    now = now or datetime.now(timezone.utc)
    if s.status == SHIP_AWAITING:
        return now - s.created_at > PICKUP_REMIND_AFTER
    if s.status == SHIP_IN_TRANSIT and s.arrived_at is None and s.picked_up_at is not None:
        return now - s.picked_up_at > ARRIVAL_REMIND_AFTER
    return False


def sweep_reminders(db: Session) -> int:
    """Run now and then by the job loop: one reminder each for a bag nobody collected and a package nobody has checked in.
    -> how many were sent."""
    now = datetime.now(timezone.utc)
    sent = 0
    for s in db.query(Shipment).filter(Shipment.status == SHIP_AWAITING, Shipment.pickup_reminded_at.is_(None), Shipment.created_at < now - PICKUP_REMIND_AFTER):
        order = db.get(Order, s.order_id)
        if order is not None:
            _notify(db, _seller_user_id(order), f"Order {str(order.id)[:8]} has been waiting over a day and no driver has collected it. {APP_NAME} is chasing the courier.", order, seller=True)
        s.pickup_reminded_at = now
        sent += 1
    for s in db.query(Shipment).filter(
        Shipment.status == SHIP_IN_TRANSIT, Shipment.transit_reminded_at.is_(None), Shipment.arrived_at.is_(None), Shipment.picked_up_at < now - ARRIVAL_REMIND_AFTER
    ):
        order = db.get(Order, s.order_id)
        if order is not None:
            _notify(db, order.buyer_id, "Has your package arrived? When it does, open My Orders and tap \"Package arrived?\" to check the seal.")
        s.transit_reminded_at = now
        sent += 1
    db.commit()
    return sent


def find_terminal_shipment(db: Session, terminal_shipment_id: str) -> "Shipment | None":
    return db.query(Shipment).filter(Shipment.courier == "terminal", Shipment.courier_ref == terminal_shipment_id).first()


def handle_terminal_event(db: Session, payload: dict) -> str:
    """One verified webhook from Terminal Africa -> what was done ("picked_up", "delivered", "cancelled", "noted" or "ignored").
    Safe to receive twice (Terminal may retry): a second in-transit finds the shipment already moved and does nothing.

    Deliberately NOT done: `shipment.delivered` does not deliver the order. Delivery here is proven by the buyer's code read to the
    driver (confirm_delivery); a driver pressing "delivered" in Terminal's own system is not proof and must not start the payout clock."""
    event = payload.get("event") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    ref = data.get("shipment") if isinstance(data, dict) else None
    if not isinstance(event, str) or not isinstance(ref, str):
        return "ignored"
    ship = find_terminal_shipment(db, ref)
    if ship is None:
        return "ignored"  # not one of ours (another system on the same Terminal account, or a test)
    if event == "shipment.in-transit":
        if ship.status != SHIP_AWAITING:
            return "ignored"
        try:
            mark_picked_up(db, ship.id, None)
        except seals.SealError:
            return "ignored"  # moved on between the check and the lock
        return "picked_up"
    if event == "shipment.cancelled":
        if ship.status != SHIP_AWAITING:
            return "ignored"
        order = db.get(Order, ship.order_id)
        if order is not None:
            _notify(db, _seller_user_id(order), f"The courier cancelled the pickup for order {str(order.id)[:8]}. {APP_NAME} is arranging another driver.", order, seller=True)
            db.commit()
        log.warning("Terminal cancelled the pickup for shipment %s (order %s): needs another pickup request", ship.id, ship.order_id)
        return "cancelled"
    if event == "shipment.delivered":
        if ship.bag_id is None:
            # No sealed bag, so no buyer code to wait for: the courier's word is the only delivery evidence there is.
            if ship.status == SHIP_AWAITING:
                try:
                    mark_picked_up(db, ship.id, None)  # Terminal skipped the in-transit event: the pickup happened, record it first
                except seals.SealError:
                    return "ignored"
            return "delivered" if mark_courier_delivered(db, ship.id) else "ignored"
        log.info("Terminal reports shipment %s delivered; waiting for the buyer's code before marking the order delivered", ship.id)
        return "noted"
    return "ignored"
