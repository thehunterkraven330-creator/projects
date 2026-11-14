import logging
import os
import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import DeliveryCompany, MerchantAccount, User
from app.shippable import is_collect_only, product_chargeable_grams
from app.schemas import ShippingAddress

log = logging.getLogger(__name__)

# Used only when no DeliveryCompany row is active at all (a fresh
# database before seed.py has run, or every company's is_active toggled
# off) — never a per-merchant or per-product fallback the way this used
# to be back when shipping settings lived on MerchantAccount. Delivery
# pricing is entirely the active company's business now; this constant
# exists purely so checkout still works with a sane number instead of
# erroring when the platform hasn't configured a courier yet.
DEFAULT_SHIPPING_FLAT_FEE = Decimal(os.environ.get("DEFAULT_SHIPPING_FLAT_FEE", "4.99"))


def resolve_shipping_address(db: Session, user: User, submitted: ShippingAddress | None) -> dict:
    """The single place both checkout paths (orders.py's legacy
    no-payment route, payments.py's real one) turn "whatever address the
    request carried, if any" into an actual address dict ready to
    snapshot onto an Order/Payment — and the single place that updates
    the user's saved default to match, so an address used at checkout is
    remembered as "last used" without the frontend needing a separate
    save step or a "save this address" checkbox.

    Shared as its own module rather than duplicated per-router the way
    each router's own small _snapshot_order is (see that function's own
    comment on why that one's copied, not shared) — this is meaningfully
    more logic, with a real failure mode (see the 400 below) worth
    getting right in exactly one place, same reasoning as reserve_stock
    living in app/inventory.py instead of being duplicated too.

    Raises 400 if there's nothing to resolve to: no address on the
    request and none saved yet either. Doesn't commit — callers already
    have their own transaction (an Order/Payment row being created in
    the same one) and a saved-default update here should roll back
    together with that, not commit independently of whether the rest of
    the checkout actually succeeds.
    """
    if submitted is not None:
        address = submitted.model_dump()
        user.set_shipping_address(address)
        return address
    if user.shipping_address is not None:
        if os.environ.get("COURIER", "manual").lower() == "terminal":
            # The courier needs a two-letter country, a postal code and a real phone number; addresses saved before that was
            # asked for ("Nigeria", no postal code) would only fail later, when the driver is booked. Ask for them now.
            from pydantic import ValidationError

            from app.schemas import ShippingAddressIn

            try:
                return ShippingAddressIn.model_validate(user.shipping_address).model_dump()
            except ValidationError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Please update your delivery address (country, postal code and phone number) before paying.",
                ) from exc
        return user.shipping_address
    raise HTTPException(
        status_code=400,
        detail="A shipping address is required — none was provided and none is saved on this account.",
    )


def group_cart_by_merchant(cart_items) -> dict[uuid.UUID | None, Decimal]:
    """The `merchant_subtotals` compute_shipping_fee needs, built once
    here instead of separately in payments.py's cart-mode initialize and
    orders.py's checkout() — both group the same CartItem rows by
    product.merchant_id the same way, so there's exactly one place that
    decides what "this merchant's share of the cart" means.
    """
    subtotals: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in cart_items:
        subtotals[item.product.merchant_id] += Decimal(str(item.product.sale_price)) * item.quantity
    return dict(subtotals)


def compute_shipping_fee(db: Session, merchant_subtotals: dict[uuid.UUID | None, Decimal]) -> Decimal:
    """Delivery-fee logic for a checkout, real multi-merchant-aware —
    not a single flat number tacked onto every order. `merchant_subtotals`
    is each distinct merchant represented in this checkout (grouped by
    group_cart_by_merchant above; None for products with no merchant)
    mapped to the sum of that merchant's own line totals (price *
    quantity, before shipping) — kept as a per-merchant grouping because
    physically these are still separate parcels from separate sellers
    even when the same courier delivers all of them, the same way
    ordering from three different sellers on a real marketplace still
    means three separate shipments and (usually) three separate shipping
    lines.

    The rate and free-shipping threshold applied to every one of those
    parcels both come from the same place now, though: whichever single
    DeliveryCompany has is_active=True — not the merchant. A merchant
    selling the product has no say in what it costs to ship it; that's
    the courier's business, priced identically for every seller on the
    platform. A cart spanning three merchants can still owe shipping to
    two of them and get free shipping from the third, because each
    parcel's own subtotal is checked against the threshold independently
    — a cart-wide total would let one cheap item from merchant A
    quietly count toward merchant B's parcel clearing the threshold it
    never actually reached on its own.

    Falls back to DEFAULT_SHIPPING_FLAT_FEE with no free-shipping tier
    if no company is currently active. If more than one row is active
    at once (nothing currently prevents that — see DeliveryCompany's own
    comment), whichever one the query happens to return first is used
    for the entire checkout; there's no per-order assignment of a
    specific company yet, so "more than one active" isn't a state this
    function can meaningfully split across correctly today.

    Called from both /payments/initialize (payments.py) and buy_now/
    checkout (orders.py, the legacy no-payment path) so the two checkout
    paths can't quietly disagree about what shipping costs for the same
    cart.
    """
    flat_fee, threshold = _flat_rule(db)

    total = Decimal("0")
    for subtotal in merchant_subtotals.values():
        if threshold is not None and subtotal >= threshold:
            continue
        total += flat_fee
    return total


def _env_money(name: str) -> "Decimal | None":
    raw = os.environ.get(name, "").strip()
    try:
        return Decimal(raw) if raw else None
    except Exception:
        return None


def _flat_rule(db: Session, country: "str | None" = None) -> "tuple[Decimal, Decimal | None]":
    """The flat delivery fee and the free-delivery threshold, in the checkout currency. SHIPPING_FLAT_FEE and
    FREE_SHIPPING_THRESHOLD (settings) win when set: the seeded delivery company carries dollar-sized numbers (4.99, 50), which
    mean nothing in naira and there is no screen to edit them. FREE_SHIPPING_THRESHOLD=0 switches free delivery off.
    With several countries open each can have its own: SHIPPING_FLAT_FEE_NG, FREE_SHIPPING_THRESHOLD_US, and so on win over the
    plain names. A country with neither set and no env override falls to the seeded dollar-sized numbers, so set one per country."""
    company = db.query(DeliveryCompany).filter(DeliveryCompany.is_active.is_(True)).first()
    cc = (country or "").strip().upper()
    fee = _env_money(f"SHIPPING_FLAT_FEE_{cc}") if cc else None
    if fee is None:
        fee = _env_money("SHIPPING_FLAT_FEE")
    if fee is None:
        fee = company.shipping_flat_fee if company is not None else DEFAULT_SHIPPING_FLAT_FEE
    threshold = _env_money(f"FREE_SHIPPING_THRESHOLD_{cc}") if cc else None
    if threshold is None:
        threshold = _env_money("FREE_SHIPPING_THRESHOLD")
    if threshold is None:
        threshold = company.free_shipping_threshold if company is not None else None
    elif threshold <= 0:
        threshold = None
    return fee, threshold


def compute_checkout_shipping(db: Session, shipping_address: dict, lines: list) -> Decimal:
    """What the buyer pays for delivery, from the address they gave and what they are buying. `lines` is [(Product, quantity)].

    With COURIER=terminal each seller's share is priced live: the courier's cheapest rate for one unit, from that seller's pickup
    address to the buyer, times the units (every unit is its own sealed bag and its own shipment), converted into the checkout
    currency with the buffer on top (app/terminal.py). The free-shipping threshold still applies per seller, as before.
    Anything that stops a live price (no key, Terminal down, no conversion rate set, a seller with no pickup address, an address
    the courier cannot use) falls back to the flat fee for that seller and is logged, so checkout never stops on a courier outage.
    Without COURIER=terminal this is exactly the flat-fee behaviour of compute_shipping_fee."""
    flat_fee, threshold = _flat_rule(db, shipping_address.get("country"))
    by_merchant: dict = defaultdict(list)
    subtotals: dict = defaultdict(lambda: Decimal("0"))
    for product, qty in lines:
        if is_collect_only(product):
            continue  # collected in person: nothing is posted, so no delivery fee
        by_merchant[product.merchant_id].append((product, qty))
        subtotals[product.merchant_id] += Decimal(str(product.sale_price)) * qty
    live = os.environ.get("COURIER", "manual").lower() == "terminal"
    total = Decimal("0")
    for merchant_id, subtotal in subtotals.items():
        if threshold is not None and subtotal >= threshold:
            continue
        fee = _live_fee(db, merchant_id, by_merchant[merchant_id], shipping_address) if live else None
        total += fee if fee is not None else flat_fee
    return total


def _live_fee(db: Session, merchant_id, lines: list, shipping_address: dict) -> "Decimal | None":
    from app import terminal
    from app.courier import pickup_address_of

    merchant = db.get(MerchantAccount, merchant_id) if merchant_id is not None else None
    pickup_raw = pickup_address_of(merchant)
    if pickup_raw is None:
        log.warning("shipping: seller %s has no pickup address; using the flat fee", merchant_id)
        return None
    try:
        pickup = terminal.address_payload(
            first_name=pickup_raw["first_name"], last_name=pickup_raw["last_name"], email=pickup_raw["email"],
            phone=pickup_raw["phone"], line1=pickup_raw["line1"], line2=pickup_raw["line2"], city=pickup_raw["city"],
            state=pickup_raw["state"], country=pickup_raw["country"], zip_code=pickup_raw["zip"], residential=False,
        )
        first, last = terminal.split_name(shipping_address.get("recipient_name", ""))
        delivery = terminal.address_payload(
            first_name=first, last_name=last, email=None, phone=shipping_address["phone"], line1=shipping_address["line1"],
            line2=shipping_address.get("line2"), city=shipping_address["city"], state=shipping_address.get("state"),
            country=shipping_address["country"], zip_code=shipping_address.get("postal_code"),
        )
        currency = terminal.checkout_currency(shipping_address.get("country"))
        fee = Decimal("0")
        for product, qty in lines:
            fee += qty * terminal.quote_unit_shipping(
                pickup, delivery, name=product.name, value=Decimal(str(product.sale_price)),
                weight_grams=product_chargeable_grams(product), currency=currency,
            )
        return fee
    except (terminal.TerminalError, ValueError, KeyError) as exc:
        log.warning("shipping: no live rate for seller %s (%s); using the flat fee", merchant_id, exc)
        return None
