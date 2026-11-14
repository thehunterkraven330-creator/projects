"""The courier behind a shipment, kept behind one small interface so a real one (Terminal Africa, ...) can replace the manual one
without touching anything else.

What a courier has to do:
  * request_pickup(shipment, order): ask for a driver. A real courier is called here and returns its own reference.
  * tell us when the driver accepted (-> shipments.mark_picked_up) and when the delivery code was confirmed
    (-> shipments.confirm_delivery). A real courier does that by calling /courier/... (or its webhook); the manual one is
    driven by an admin in Admin > Shipments.

Choose with COURIER (default "manual"; "terminal" = Terminal Africa, app/terminal.py). Adding one = a class and a branch in get_courier.
"""
import os
from typing import Protocol


class Courier(Protocol):
    name: str

    def request_pickup(self, shipment, order) -> "str | None":
        """Ask for a driver. -> the courier's own reference for the job, or None. The collection point is
        pickup_address_for(order) below (the seller's saved pickup address)."""


class ManualCourier:
    """No outside service: an admin marks the pickup and enters the delivery code (Admin > Shipments)."""

    name = "manual"

    def request_pickup(self, shipment, order) -> "str | None":
        return None


def pickup_address_for(order) -> "dict | None":
    """The seller's pickup address for this order, shaped for Terminal Africa's address API (see pickup_address_of)."""
    merchant = order.product.merchant if order.product is not None else None
    return pickup_address_of(merchant)


def pickup_address_of(merchant) -> "dict | None":
    """A seller's pickup address shaped the way Terminal Africa's address API takes it (first_name, last_name, email, phone,
    line1, line2, city, state, country as an ISO code, zip). None if the seller has not given a complete address."""
    if merchant is None or not merchant.has_pickup_address:
        return None
    parts = merchant.pickup_contact_name.split(None, 1)
    return {
        "first_name": parts[0],
        "last_name": parts[1] if len(parts) > 1 else parts[0],  # the API wants both; a single name is used for each
        "email": merchant.user.email if merchant.user is not None else None,
        "phone": merchant.pickup_phone,
        "line1": merchant.pickup_line1,
        "line2": merchant.pickup_line2 or "",
        "city": merchant.pickup_city,
        "state": merchant.pickup_state,
        "country": merchant.pickup_country,
        "zip": merchant.pickup_postal_code or "",
    }


_COURIERS = {"manual": ManualCourier}


def get_courier() -> Courier:
    name = os.environ.get("COURIER", "manual").lower()
    if name == "terminal":
        from app.terminal import TerminalCourier  # only when chosen: it needs httpx and the Terminal key

        return TerminalCourier()
    return _COURIERS.get(name, ManualCourier)()


def courier_key_ok(given: "str | None") -> bool:
    """The shared secret a courier's system sends in X-Courier-Key (COURIER_API_KEY). Off (always False) when unset."""
    import hmac

    key = os.environ.get("COURIER_API_KEY", "")
    return bool(key) and bool(given) and hmac.compare_digest(key, given)


def courier_tracks_orders() -> bool:
    """True when a real courier is connected, so its events (not the seller) move an order to shipped and delivered."""
    return os.environ.get("COURIER", "manual").lower() != "manual"
