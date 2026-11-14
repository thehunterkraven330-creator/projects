import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import claim_review, courier, seal_packs, shipments, sponsored
from app.attribution import resolve_source_post
from app.auth import get_current_active_user
from app.notifications import notify_new_order
from app.database import get_db
from app import scan_service
from app.escrow import release_to_merchant, sweep_auto_releases
from app.inventory import release_stock, reserve_stock
from app.models import CartItem, Notification, NotificationType, Order, OrderStatus, PaymentStatus, PayoutStatus, Product, ReturnClaim, ReturnClaimStatus, User
from app.gateway import refund_transaction
from app.payment_provider import provider_of
from app.return_policy import validate_return_claim
from app.schemas import (
    CheckoutCreate,
    ClaimAppeal,
    ClaimMine,
    OrderCancelRequest,
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
    ReturnClaimCreate,
    ReturnClaimRead,
    ReturnClaimSellerResponse,
)
from app.models.collect import NOSHOW_CLAIMED, NOSHOW_DISPUTED, CollectNoShow
from app.shippable import is_collect_only
from app.shipping import resolve_shipping_address

router = APIRouter(prefix="/orders", tags=["orders"])

# The only status change a seller may make by hand (see advance_order_status). Cancelling is a separate route.
_NEXT_STATUS = {OrderStatus.pending: OrderStatus.shipped, OrderStatus.shipped: OrderStatus.delivered}


def _snapshot_order(
    db: Session,
    buyer: User,
    product: Product,
    color: str | None,
    size: str | None,
    shipping_address: dict,
    source_video_post_id: uuid.UUID | None = None,
    sponsored_twin_id: uuid.UUID | None = None,
) -> Order:
    """Every Order field below is a snapshot of the buyer/product/address
    at this exact moment — see the comment on the Order model for why
    (renames, deletions, address changes, and display-name changes
    shouldn't rewrite order history)."""
    order = Order(
        buyer_id=buyer.id,
        product_id=product.id,
        product_name=product.name,
        price=product.sale_price,
        color=color,
        size=size,
        buyer_name=buyer.display_name,
        source_video_post_id=source_video_post_id,
    )
    sponsored.apply_to_order(order, sponsored_twin_id)
    order.collect_in_person = is_collect_only(product)
    order.set_shipping_address(shipping_address)
    db.add(order)
    notify_new_order(db, order, buyer, product)
    return order


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def buy_now(
    payload: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Maps to handleBuyNow / handleBuyNowFromShopFeed — an immediate
    order that never touches the cart, same as the frontend's "Buy now"
    button on a product card. This is the legacy no-payment path (the
    frontend now goes through /payments/initialize + /payments/verify
    instead) but it's still a live, callable route, so it gets the same
    stock enforcement — and now the same shipping-address requirement —
    as everywhere else that creates an Order.
    """
    shipping_address = resolve_shipping_address(db, current_user, payload.shipping_address)
    product = reserve_stock(db, payload.product_id, 1)

    source_post = resolve_source_post(db, payload.source_video_post_id, product.id)
    order = _snapshot_order(
        db,
        current_user,
        product,
        payload.color,
        payload.size,
        shipping_address,
        source_post.id if source_post is not None else None,
        sponsored.resolve_twin(db, payload.sponsored_twin_id, product.id),
    )
    db.commit()
    db.refresh(order)
    seal_packs.assign_pending(db, [order])
    seal_packs.annotate(db, [order])
    return order


@router.post("/checkout", response_model=list[OrderRead], status_code=status.HTTP_201_CREATED)
def checkout(
    payload: CheckoutCreate = CheckoutCreate(),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Maps to handleCheckout. One Order per unit of quantity — a cart
    line with quantity 3 becomes 3 separate orders, matching the
    frontend's Array.from({length: item.quantity}) expansion — then the
    cart is cleared. All lines in one checkout ship to the same address,
    same as a real cart checkout normally works.
    """
    shipping_address = resolve_shipping_address(db, current_user, payload.shipping_address)
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    new_orders: list[Order] = []
    for item in cart_items:
        product = reserve_stock(db, item.product_id, item.quantity)
        for _ in range(item.quantity):
            new_orders.append(
                _snapshot_order(
                    db, current_user, product, item.color, item.size, shipping_address, item.source_video_post_id, item.sponsored_twin_id
                )
            )
        db.delete(item)

    db.commit()
    for order in new_orders:
        db.refresh(order)
    seal_packs.assign_pending(db, new_orders)
    seal_packs.annotate(db, new_orders)
    return new_orders


def _mark_holds(db: Session, orders: list[Order]) -> None:
    """Flag the orders whose payout is paused by a copy review of the seller's own video (OrderRead.payout_on_hold)."""
    held = scan_service.payout_hold_ids(db, orders)
    for order in orders:
        order.payout_on_hold = order.id in held


@router.get("/me", response_model=list[OrderRead])
def list_my_orders(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Orders the current user placed as a buyer."""
    orders = (
        db.query(Order)
        .filter(Order.buyer_id == current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    # Opportunistic, not scheduled — see sweep_auto_releases' own
    # comment for why "whenever someone happens to check their orders"
    # is what this app can actually do right now.
    sweep_auto_releases(db, orders)
    _mark_holds(db, orders)
    seal_packs.annotate(db, orders)
    return orders


@router.get("/selling", response_model=list[OrderRead])
def list_orders_to_fulfill(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Powers the merchant dashboard's Orders tab (MerchantOrders.tsx) —
    every order placed against one of the current user's products,
    regardless of who bought it."""
    if current_user.merchant_account is None:
        raise HTTPException(status_code=404, detail="No merchant account for this user")
    orders = (
        db.query(Order)
        .join(Product, Order.product_id == Product.id)
        .filter(Product.merchant_id == current_user.merchant_account.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    sweep_auto_releases(db, orders)
    _mark_holds(db, orders)
    seal_packs.assign_pending(db, [o for o in orders if o.status == OrderStatus.pending])  # the shop's bag packs waiting for stock
    seal_packs.annotate(db, orders)
    return orders


@router.patch("/{order_id}/status", response_model=OrderRead)
def advance_order_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Maps to handleAdvanceOrderStatus — merchant-only, and only for
    orders against that merchant's own products. Doesn't enforce the
    frontend's pending → shipped → delivered forward-only ordering (that
    lives in MerchantOrders' UI, which only ever offers the next status
    as a button) — worth adding here too if this ever gets a second
    client that isn't as well-behaved.
    """
    order = db.get(Order, order_id)
    merchant = current_user.merchant_account
    if (
        order is None
        or merchant is None
        or order.product is None
        or order.product.merchant_id != merchant.id
    ):
        raise HTTPException(status_code=404, detail="Order not found")

    # Only the next step forward, one at a time: pending -> shipped -> delivered. Without this a seller could mark an order
    # "delivered" straight from pending (or after it was cancelled and refunded), which starts the 24-hour clock after which
    # the money is paid out to them, with nothing ever sent. Cancelling has its own route (POST /orders/{id}/cancel).
    if payload.status != order.status and _NEXT_STATUS.get(order.status) != payload.status:
        raise HTTPException(
            status_code=409,
            detail=f"An order that is {order.status.value} can't be changed to {payload.status.value}.",
        )

    from app import seals

    if payload.status in (OrderStatus.shipped, OrderStatus.delivered) and seals.sealed_test_for(db, order.id) is not None:
        # A sealed order is tracked by its bag: the courier's pickup sets "shipped" and the buyer's scan with the driver's
        # code sets "delivered" (which starts the claim window). A seller can't start that clock themselves.
        raise HTTPException(
            status_code=409, detail="This order is tracked by its sealed bag. Its status updates automatically."
        )
    if payload.status in (OrderStatus.shipped, OrderStatus.delivered):
        # Never the seller: the platform's courier (its pickup and delivery events, or an admin standing in for it) says when a
        # parcel left and when it arrived.
        raise HTTPException(
            status_code=409,
            detail='Tap "Ready for pickup" and the courier\'s progress updates this order by itself.',
        )
    order.status = payload.status
    if payload.status == OrderStatus.delivered and order.delivered_at is None:
        # Starts the 24-hour claim window (app/return_policy.py's
        # CLAIM_WINDOW) ticking from exactly this moment, not from
        # updated_at — see delivered_at's own comment on the Order
        # model for why those two need to stay separate.
        order.delivered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/ready-for-pickup", response_model=OrderRead)
def ready_for_pickup(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """An order sent WITHOUT a live test: the seller says it is packed and the courier is asked for a driver. From then on the
    courier's progress (pickup, delivery) moves the order. Tapping again only re-asks the courier if the first request failed."""
    order = db.get(Order, order_id)
    merchant = current_user.merchant_account
    if order is None or merchant is None or order.product is None or order.product.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail=f"An order that is {order.status.value} can't be sent for pickup.")
    from app import seals

    if order.collect_in_person:
        raise HTTPException(status_code=409, detail="This order is collected in person: the buyer comes to your pickup address. Nothing to send.")
    if seals.sealed_test_for(db, order.id) is not None or seal_packs.pack_size_of(db, order) > 0:
        raise HTTPException(status_code=409, detail="This order is tracked by its sealed bag.")
    if not merchant.has_pickup_address:
        raise HTTPException(status_code=409, detail="Add your pickup address in your shop settings first, so the driver knows where to collect.")
    existing = shipments.get_for_order(db, order.id)
    if existing is not None:
        shipments.retry_pickup(db, existing, order)
    else:
        shipments.create_for_order(db, order)
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderRead)
def cancel_order(
    order_id: uuid.UUID,
    payload: OrderCancelRequest = OrderCancelRequest(),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Either the buyer or the selling merchant can cancel — a buyer
    changing their mind and a merchant who can't fulfill something are
    both real, common reasons this needs to happen, and there's no
    reason to make them two separate endpoints that do the same work.
    Only allowed before delivery: once something has actually arrived,
    "I don't want this" is a return, which this app doesn't model, not
    a cancellation.

    Refunds through Paystack whenever the order was genuinely paid for
    (payment_id set, and that payment succeeded) — legacy orders from
    before payments existed, or ones this same route already cancelled,
    have nothing to refund and just get skipped straight to the status
    change. The refund is partial, for exactly this order's own
    product price, not the whole Payment: one Payment can fund several
    Order rows (a cart checkout), and cancelling one shouldn't refund
    the others' share along with it. It does NOT prorate shipping_fee
    or discount_amount back for a single cancelled line out of a
    multi-item order — a known simplification, not an oversight: doing
    that fairly needs real per-line cost accounting this app doesn't
    have yet.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    is_buyer = order.buyer_id == current_user.id
    is_selling_merchant = (
        current_user.merchant_account is not None
        and order.product is not None
        and order.product.merchant_id == current_user.merchant_account.id
    )
    if not is_buyer and not is_selling_merchant:
        # Same 404-not-403 pattern as every other ownership check in this
        # app — doesn't confirm this order id exists at all to someone
        # who has no business with it.
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=400, detail="This order is already cancelled")
    if order.status == OrderStatus.delivered:
        raise HTTPException(status_code=400, detail="Delivered orders can't be cancelled")

    from app import order_cancel, seals as _seals

    try:
        order_cancel.cancel_and_refund(db, order, payload.reason)
    except _seals.SealError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    db.refresh(order)
    return order


@router.post("/{order_id}/confirm-receipt", response_model=OrderRead)
def confirm_receipt(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The buyer's explicit "yes, this is what I ordered — pay the
    merchant" tap. Releases this order's held funds right away instead
    of waiting out the rest of the 24-hour claim window (see
    CLAIM_WINDOW in app/return_policy.py, and sweep_auto_releases in
    app/escrow.py for what happens if a buyer never taps this at all).
    Buyer-only — a merchant can't release their own funds by calling
    this themselves.
    """
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.delivered:
        raise HTTPException(status_code=400, detail="This order hasn't been delivered yet")

    release_to_merchant(db, order)
    db.refresh(order)
    return order


class ComingBody(BaseModel):
    """The buyer tells the seller when they plan to come. The place is always the seller's saved pickup address."""
    when: datetime
    when_label: str = Field(min_length=3, max_length=60)  # that moment as the buyer's own phone shows it, e.g. "Sat 14 Nov, 10:00"


@router.post("/{order_id}/coming", response_model=OrderRead)
def collect_coming(
    order_id: uuid.UUID,
    payload: ComingBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Collect-in-person order: the buyer taps "I'm coming on ...". The seller is notified so someone is there. May be changed."""
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.collect_in_person or order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail="This order can't take a visit time.")
    when = payload.when if payload.when.tzinfo is not None else payload.when.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    deadline = order.collect_deadline
    if when <= now or (deadline is not None and when > deadline):
        raise HTTPException(status_code=422, detail="Choose a time from now until the end of your collection window.")
    order.visit_details_at = when
    order.visit_details = payload.when_label.strip()
    if order.product is not None and order.product.merchant is not None:
        db.add(Notification(
            user_id=order.product.merchant.user_id,
            body=f"{order.buyer_name} plans to come and collect {order.product_name} on {order.visit_details}. Please make sure someone is there.",
            type=NotificationType.order,
            audience="seller",
            actor_id=current_user.id,
            target_id=order.id,
        ))
    db.commit()
    db.refresh(order)
    return order


def _collect_group(db: Session, order: Order) -> list[Order]:
    """The units bought together (same payment, same product) that are still waiting: a buyer collecting 5 units inspects them once
    and accepts or rejects them all with one tap. Just this order when it has no payment to group by."""
    if order.payment_id is None:
        return [order]
    return (
        db.query(Order)
        .filter(
            Order.payment_id == order.payment_id,
            Order.product_id == order.product_id,
            Order.buyer_id == order.buyer_id,
            Order.collect_in_person.is_(True),
            Order.status == OrderStatus.pending,
        )
        .order_by(Order.created_at)
        .all()
    ) or [order]


class NoShowReplyBody(BaseModel):
    note: str = Field(default="", max_length=500)
    photo_url: str | None = Field(default=None, max_length=600)


class OpenNoShow(BaseModel):
    order_id: uuid.UUID
    kind: str = "not_there"
    product_name: str | None = None
    buyer_note: str | None = None
    buyer_photo_url: str
    planned_for: datetime | None = None
    status: str
    replied: bool
    reply_by: datetime


NOSHOW_REPLY_HOURS = 48


@router.get("/noshow-claims/mine", response_model=list[OpenNoShow])
def my_noshow_claims(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """The seller's open "nobody was there" claims, so they can answer them."""
    merchant = current_user.merchant_account
    if merchant is None:
        return []
    rows = (
        db.query(CollectNoShow)
        .filter(CollectNoShow.merchant_id == merchant.id, CollectNoShow.status.in_([NOSHOW_CLAIMED, NOSHOW_DISPUTED]))
        .order_by(CollectNoShow.created_at.desc())
        .limit(50)
        .all()
    )
    out = []
    for c in rows:
        order = db.get(Order, c.order_id)
        out.append(OpenNoShow(
            order_id=c.order_id, kind=c.kind, product_name=order.product_name if order else None, buyer_note=c.note, buyer_photo_url=c.photo_url,
            planned_for=c.planned_for, status=c.status, replied=c.seller_replied_at is not None,
            reply_by=c.created_at + timedelta(hours=NOSHOW_REPLY_HOURS),
        ))
    return out


@router.post("/{order_id}/noshow-reply", response_model=dict[str, bool])
def reply_to_noshow(
    order_id: uuid.UUID,
    payload: NoShowReplyBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The seller answers a "nobody was there" claim: a note and a photo taken at their pickup address. An admin then decides."""
    merchant = current_user.merchant_account
    claim = db.query(CollectNoShow).filter(CollectNoShow.order_id == order_id).one_or_none()
    if claim is None or merchant is None or claim.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status not in (NOSHOW_CLAIMED, NOSHOW_DISPUTED):
        raise HTTPException(status_code=409, detail="This claim has already been decided.")
    if datetime.now(timezone.utc) > claim.created_at + timedelta(hours=NOSHOW_REPLY_HOURS):
        raise HTTPException(status_code=409, detail="The time to reply has passed. An admin will decide from the buyer's evidence.")
    if len(payload.note.strip()) < 3:
        raise HTTPException(status_code=422, detail="Tell us what happened.")
    claim.seller_note = payload.note.strip()
    claim.seller_photo_url = _own_photo(payload.photo_url) if payload.photo_url else None
    claim.seller_replied_at = datetime.now(timezone.utc)
    claim.status = NOSHOW_DISPUTED
    db.commit()
    return {"ok": True}


@router.post("/{order_id}/collect-accept", response_model=OrderRead)
def collect_accept(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The buyer, in front of the item, taps Accept: the order is delivered and the seller is paid now. The seller hands the item over
    when they see the order marked delivered on their side."""
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.collect_in_person:
        raise HTTPException(status_code=409, detail="This order is delivered by courier.")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail="This order can't be accepted.")
    group = _collect_group(db, order)
    now = datetime.now(timezone.utc)
    for o in group:
        o.status = OrderStatus.delivered
        o.delivered_at = now
    if order.product is not None and order.product.merchant is not None:
        db.add(Notification(
            user_id=order.product.merchant.user_id,
            body=f"The buyer inspected and accepted {order.product_name}" + (f" ({len(group)} units)" if len(group) > 1 else "")
            + ". Hand the item over now. Your payment is on its way.",
            type=NotificationType.order,
            audience="seller",
            actor_id=current_user.id,
            target_id=order.id,
        ))
    db.commit()
    for o in group:
        try:
            release_to_merchant(db, o)
        except HTTPException:
            # The buyer's accept stands. A seller whose payout isn't set up is paid by the scheduled release once it is.
            db.rollback()
    db.refresh(order)
    return order


class RejectBody(BaseModel):
    # "seller_not_there": the buyer travelled and nobody was there. That counts as a strike against the seller (admins see it).
    code: Literal["not_as_described", "seller_not_there", "seller_refused", "other"] = "other"
    reason: str = Field(default="", max_length=500)
    # "seller_not_there" and "seller_refused" (the seller was there but wouldn't show or sell it) need a photo of the place, taken with the phone camera and uploaded (our own storage only).
    photo_url: str | None = Field(default=None, max_length=600)


def _own_photo(url: str | None) -> str:
    from app import storage

    if not url or storage.key_from_view_url(url) is None:
        raise HTTPException(status_code=422, detail="Take a photo of the place with your camera and attach it.")
    return url


@router.post("/{order_id}/collect-reject", response_model=OrderRead)
def collect_reject(
    order_id: uuid.UUID,
    payload: RejectBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The buyer inspected it and it isn't right: full refund, the seller keeps the item. A reason is required."""
    from app import order_cancel

    order = db.get(Order, order_id)
    if order is None or order.buyer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.collect_in_person or order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail="This order can't be rejected.")
    noshow = payload.code in ("seller_not_there", "seller_refused")  # a claim against the seller: evidence, then an admin decides
    refused = payload.code == "seller_refused"
    text = payload.reason.strip()
    if (not noshow or refused) and len(text) < 3:
        raise HTTPException(status_code=422, detail="Say what is wrong with it." if not noshow else "Say what happened.")
    photo = None
    if noshow:
        # Evidence first: the seller was told when to expect the buyer, and the time has passed, and there is a photo of the place.
        if order.visit_details_at is None:
            raise HTTPException(status_code=409, detail='Tap "I\'m coming" with the time you will be there first, so the seller knows to expect you.')
        if datetime.now(timezone.utc) < order.visit_details_at:
            raise HTTPException(status_code=409, detail="You can report this only after the time you said you would come.")
        photo = _own_photo(payload.photo_url)
    group = _collect_group(db, order)
    prefix = order_cancel.REFUSED_PREFIX if refused else order_cancel.NO_SHOW_PREFIX if noshow else order_cancel.REJECT_PREFIX
    for o in group:
        order_cancel.cancel_and_refund(db, o, f"{prefix}{text or 'nobody was there at the pickup address'}")
    merchant = order.product.merchant if order.product is not None else None
    if merchant is not None:
        if noshow:
            # No strike yet: this is a claim with evidence. The seller can answer it and an admin decides (admin > Collect in person).
            db.add(CollectNoShow(
                order_id=order.id, merchant_id=merchant.id, buyer_id=order.buyer_id, planned_for=order.visit_details_at,
                photo_url=photo, note=text or None, kind="refused" if refused else "not_there",
            ))
        db.add(Notification(
            user_id=merchant.user_id,
            body=(
                f"The buyer says they came to your pickup address for {order.product_name} at the time they told you and you would not show "
                f"or sell it to them ({text}). They were refunded. If that is wrong, open Orders and reply within 48 hours."
                if refused
                else f"The buyer says they went to your pickup address for {order.product_name} at the time they told you, and nobody was there. "
                "They were refunded. If that is wrong, open Orders and reply with a photo from your pickup address within 48 hours."
                if noshow
                else f"The buyer rejected {order.product_name}" + (f" ({len(group)} units)" if len(group) > 1 else "")
                + f" after inspecting it ({text}). They were refunded."
            ),
            type=NotificationType.order,
            audience="seller",
            actor_id=current_user.id,
            target_id=order.id,
        ))
        db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/report-defect", response_model=OrderRead)
def report_defect(
    order_id: uuid.UUID,
    payload: ReturnClaimCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The buyer's "this arrived defective / not as described" path.
    validate_return_claim (app/return_policy.py) is the filter deciding
    whether a claim is even allowed to be FILED — delivered status,
    still inside the 24-hour window, a video present — and this route
    doesn't duplicate any of that logic itself, only calls into it.

    Filing no longer refunds in the same request — the claim is created
    `pending_review` (ReturnClaim's own default) and sits there until an
    admin resolves it via routers/admin.py, which is the only place
    refund_for_defect (app/escrow.py) gets called from now. The order's
    payout_status is left exactly as it was (still `held`) — see
    sweep_auto_releases in app/escrow.py, which now checks for an open
    claim before releasing funds, so this doesn't race a merchant
    getting paid out while a claim against the same order is still
    sitting unreviewed.
    """
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.collect_in_person:
        raise HTTPException(status_code=409, detail="You inspected this in person before accepting it, so it can't be reported afterwards.")

    validate_return_claim(order, payload.video_url)

    if db.query(ReturnClaim).filter(ReturnClaim.order_id == order.id).first() is not None:
        raise HTTPException(status_code=400, detail="A claim has already been filed for this order")

    reasons = claim_review.clean_reasons(payload.reasons)
    if not reasons and not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Choose what's wrong, or describe it")
    claim = ReturnClaim(
        order_id=order.id,
        buyer_id=current_user.id,
        video_url=payload.video_url,
        reason=payload.reason,
        reasons=reasons,
    )
    db.add(claim)
    db.commit()
    claim_review.auto_decide(db, claim)  # AUTO_REFUND_CLEAR_CASES: a clear buyer win is refunded now, anything else waits for a person
    db.refresh(order)
    return order


@router.get("/claims/mine", response_model=list[ClaimMine])
def my_claims(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Every claim the user is part of, as buyer or as the selling merchant, with whether they may still appeal it."""
    from app import claim_review

    out = []
    q = db.query(ReturnClaim).join(Order, Order.id == ReturnClaim.order_id)
    mine = q.filter(ReturnClaim.buyer_id == current_user.id).all()
    seller = []
    if current_user.merchant_account is not None:
        seller = q.join(Product, Product.id == Order.product_id).filter(Product.merchant_id == current_user.merchant_account.id).all()
    for role, claims in (("buyer", mine), ("seller", seller)):
        for c in claims:
            side = claim_review.appeal_side(c)
            out.append(
                ClaimMine(
                    order_id=c.order_id, role=role, status=c.status, auto_resolved=c.auto_resolved, resolution_note=c.resolution_note,
                    can_appeal=side == role, appeal_by=c.appeal_by, appeal_outcome=c.appeal_outcome,
                )
            )
    return out


@router.post("/{order_id}/return-claim/appeal", response_model=ReturnClaimRead)
def appeal_return_claim(
    order_id: uuid.UUID,
    payload: ClaimAppeal,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The losing side's one appeal, within APPEAL_WINDOW_HOURS of the decision: the buyer after a denial, the seller after a refund.
    A person at Lumin then rules on it (Admin > Disputes > Appeals)."""
    from app import claim_review

    order = db.get(Order, order_id)
    claim = db.query(ReturnClaim).filter(ReturnClaim.order_id == order_id).first() if order is not None else None
    if order is None or claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    is_buyer = order.buyer_id == current_user.id
    is_seller = (
        current_user.merchant_account is not None
        and order.product is not None
        and order.product.merchant_id == current_user.merchant_account.id
    )
    role = "buyer" if is_buyer else "seller" if is_seller else None
    if role is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim_review.appeal_side(claim) != role:
        raise HTTPException(status_code=400, detail="This claim can't be appealed by you (already appealed, not decided yet, or the window has passed)")
    claim.appeal_by = role
    claim.appeal_note = (payload.note or "").strip()[:1000] or None
    claim.appealed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(claim)
    return claim


@router.get("/{order_id}/return-claim", response_model=ReturnClaimRead)
def get_return_claim(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Either party can check a claim's status — the buyer who filed it,
    or the selling merchant it was filed against. Needed now in a way it
    wasn't before: report_defect used to refund in the same request, so
    there was nothing to check back on later. Now there is, and this is
    that check.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    is_buyer = order.buyer_id == current_user.id
    is_selling_merchant = (
        current_user.merchant_account is not None
        and order.product is not None
        and order.product.merchant_id == current_user.merchant_account.id
    )
    if not is_buyer and not is_selling_merchant:
        raise HTTPException(status_code=404, detail="Order not found")

    claim = db.query(ReturnClaim).filter(ReturnClaim.order_id == order.id).first()
    if claim is None:
        raise HTTPException(status_code=404, detail="No claim has been filed for this order")
    return claim


@router.post("/{order_id}/return-claim/respond", response_model=ReturnClaimRead)
def respond_to_return_claim(
    order_id: uuid.UUID,
    payload: ReturnClaimSellerResponse,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """The selling merchant's one-shot rebuttal to a claim filed against
    one of their orders — see ReturnClaim's own comment on why this is
    deliberately a single message, not a back-and-forth thread. Only
    while the claim is still pending_review: once an admin has already
    resolved it (routers/admin.py), a rebuttal arriving after the fact
    wouldn't change anything and would be confusing to show alongside a
    decision that's already been made.
    """
    order = db.get(Order, order_id)
    if (
        order is None
        or current_user.merchant_account is None
        or order.product is None
        or order.product.merchant_id != current_user.merchant_account.id
    ):
        raise HTTPException(status_code=404, detail="Order not found")

    claim = db.query(ReturnClaim).filter(ReturnClaim.order_id == order.id).first()
    if claim is None:
        raise HTTPException(status_code=404, detail="No claim has been filed for this order")
    if claim.status != ReturnClaimStatus.pending_review:
        raise HTTPException(status_code=400, detail="This claim has already been resolved")

    claim.seller_response = payload.message
    db.commit()
    db.refresh(claim)
    return claim
