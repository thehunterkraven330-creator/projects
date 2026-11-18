"""Cancelling a paid order and refunding the buyer: the one place the steps live, used by the cancel route (a buyer or seller
cancels) and by the automatic cancels (a seller who never packs, a courier who never collects)."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import seal_packs, shipments
from app.brand import APP_NAME
from app.gateway import refund_transaction
from app.inventory import release_stock
from app.models.commerce import collect_window_days
from app.models import Notification, NotificationType, Order, OrderStatus, PaymentStatus, PayoutStatus, Shipment
from app.models.seal import SHIP_AWAITING
from app.payment_provider import provider_of

log = logging.getLogger(__name__)

# cancel_reason prefixes for a collect-in-person order the buyer turned down: the admin page groups orders by them.
REJECT_PREFIX = "Rejected after inspection: "
NO_SHOW_PREFIX = "Seller was not there: "
REFUSED_PREFIX = "Seller refused to show or sell it: "


def cancel_and_refund(db: Session, order: Order, reason: "str | None") -> None:
    """Free the bag / stop the courier booking, refund this order's own price, give the stock back, mark the order cancelled
    and the payout refunded, then commit. Raises seals.SealError if the order is already with a driver, and whatever the payment
    provider raises if the refund fails (nothing is committed in that case: the caller rolls back)."""
    shipments.on_order_cancelled(db, order)  # a sealed order: free its bag, or refuse while it is with the driver
    if order.payment is not None and order.payment.status == PaymentStatus.success:
        refund_transaction(
            order.payment.reference, amount_subunit=int(order.price * 100), order_id=order.id, provider=provider_of(order.payment)
        )
    # Only an order that hadn't shipped yet gets its stock back: once shipped, the item already left.
    if order.status == OrderStatus.pending and order.product_id is not None:
        release_stock(db, order.product_id, 1)
    order.status = OrderStatus.cancelled
    order.cancel_reason = reason
    order.payout_status = PayoutStatus.refunded
    # A Payment funding several orders only reaches "refunded" once the LAST of them is cancelled.
    if order.payment is not None and all(o.status == OrderStatus.cancelled for o in order.payment.orders):
        order.payment.status = PaymentStatus.refunded
    db.commit()
    db.refresh(order)
    seal_packs.release_for_order(db, order)  # a cancelled bag pack gives its unused bags back to the stock


# ------------------------------------------------------------------ automatic cancels
def _hours(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def pack_deadline() -> timedelta:
    """How long a seller has to tap Ready for pickup (AUTO_CANCEL_UNPACKED_HOURS, default 72)."""
    return timedelta(hours=_hours("AUTO_CANCEL_UNPACKED_HOURS", 72))


def pack_reminder_after() -> timedelta:
    """The seller is warned at this age, always before the deadline (AUTO_REMIND_UNPACKED_HOURS, default 48)."""
    return min(timedelta(hours=_hours("AUTO_REMIND_UNPACKED_HOURS", 48)), pack_deadline() - timedelta(hours=1))


def collect_deadline() -> timedelta:
    """How long the courier has to collect after Ready for pickup (AUTO_CANCEL_UNCOLLECTED_HOURS, default 72)."""
    return timedelta(hours=_hours("AUTO_CANCEL_UNCOLLECTED_HOURS", 72))


def _notify(db: Session, user_id: "uuid.UUID | None", body: str, order: "Order | None" = None, seller: bool = False) -> None:
    """seller=True: the notice is about the person's business account, so a tap opens the business Orders."""
    if user_id is not None:
        db.add(Notification(
            user_id=user_id, body=body, type=NotificationType.order,
            audience="seller" if seller else None,
            target_id=order.id if order is not None else None,
            actor_id=order.buyer_id if (seller and order is not None) else None,
        ))


def _short(order: Order) -> str:
    return str(order.id)[:8]


def _seller_id(order: Order) -> "uuid.UUID | None":
    return order.product.merchant.user_id if order.product is not None and order.product.merchant is not None else None


def _auto_cancel(db: Session, order: Order, reason: str, buyer_msg: str, seller_msg: str) -> bool:
    try:
        cancel_and_refund(db, order, reason)
    except Exception:
        db.rollback()
        log.exception("automatic cancel of order %s failed; it will be tried again", order.id)
        return False
    _notify(db, order.buyer_id, buyer_msg, order)
    _notify(db, _seller_id(order), seller_msg, order, seller=True)
    db.commit()
    return True


def sweep_unfulfilled(db: Session, now: "datetime | None" = None) -> dict:
    """Run by the job loop. Pending orders whose seller never tapped Ready for pickup (warned first, then cancelled and refunded),
    and orders whose driver was requested but never came (cancelled, refunded, the booking cancelled). Orders already with a driver are
    never touched. -> {"reminded": n, "cancelled_unpacked": n, "cancelled_uncollected": n}."""
    now = now or datetime.now(timezone.utc)
    out = {"reminded": 0, "cancelled_unpacked": 0, "cancelled_uncollected": 0}

    # 1) never packed: pending, no shipment, not a printed-bag pack order (those have their own flow)
    unpacked = (
        db.query(Order)
        .outerjoin(Shipment, Shipment.order_id == Order.id)
        .filter(
            Order.status == OrderStatus.pending,
            Shipment.id.is_(None),
            Order.created_at < now - pack_reminder_after(),
            Order.collect_in_person.is_(False),  # collect orders have their own window (below): the seller has nothing to tap
        )
        .limit(100)
        .all()
    )
    for order in unpacked:
        if seal_packs.pack_size_of(db, order) > 0:
            continue
        if order.created_at < now - pack_deadline():
            if _auto_cancel(
                db, order, "Cancelled: the seller did not send it in time",
                f"Order {_short(order)} was cancelled because the seller didn't get it ready in time. You have been refunded in full.",
                f"Order {_short(order)} was cancelled and refunded because it wasn't marked ready for pickup in time.",
            ):
                out["cancelled_unpacked"] += 1
            continue
        marker = f"Order {_short(order)} must be ready for pickup"
        sid = _seller_id(order)
        if sid is not None and db.query(Notification.id).filter(Notification.user_id == sid, Notification.body.like(f"{marker}%")).first() is None:
            left = int((order.created_at + pack_deadline() - now).total_seconds() // 3600)
            _notify(db, sid, f"{marker} within {max(left, 1)} hours or it will be cancelled and refunded to the buyer. Open Orders and tap Ready for pickup.", order, seller=True)
            db.commit()
            out["reminded"] += 1

    # 2) driver requested, never collected
    uncollected = (
        db.query(Shipment)
        .filter(Shipment.status == SHIP_AWAITING, Shipment.created_at < now - collect_deadline())
        .limit(100)
        .all()
    )
    for ship in uncollected:
        order = db.get(Order, ship.order_id)
        if order is None or order.status != OrderStatus.pending:
            continue
        if _auto_cancel(
            db, order, "Cancelled: no courier collected it in time",
            f"Order {_short(order)} was cancelled because no driver collected it in time. You have been refunded in full.",
            f"Order {_short(order)} was cancelled and refunded because no driver collected it in time. {APP_NAME} is sorry for the trouble.",
        ):
            out["cancelled_uncollected"] += 1

    # 3) collect in person: the buyer has the window from the moment they paid. One reminder a day before it ends, then cancel + refund.
    window = timedelta(days=collect_window_days())
    collecting = (
        db.query(Order)
        .filter(Order.collect_in_person.is_(True), Order.status == OrderStatus.pending, Order.created_at < now - window + timedelta(days=1))
        .limit(100)
        .all()
    )
    for order in collecting:
        if order.created_at < now - window:
            if _auto_cancel(
                db, order, "Cancelled: the item was not collected in time",
                f"Order {_short(order)} was cancelled because it wasn't collected in time. You have been refunded in full.",
                f"Order {_short(order)} was cancelled and refunded because the buyer didn't come to collect it in time. The item is still yours.",
            ):
                out["cancelled_uncollected"] += 1
            continue
        marker = f"Order {_short(order)}: your collection window ends"
        if order.buyer_id is not None and db.query(Notification.id).filter(Notification.user_id == order.buyer_id, Notification.body.like(f"{marker}%")).first() is None:
            _notify(db, order.buyer_id, f"{marker} within 24 hours. Go and inspect {order.product_name}, then accept it, or the order is cancelled and refunded.")
            db.commit()
            out["reminded"] += 1
    return out
