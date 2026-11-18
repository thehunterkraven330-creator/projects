"""Terminal Africa (TShip) client, and the courier class that books a pickup through it.

Config (environment):
  TERMINAL_AFRICA_SECRET_KEY   the secret key (sk_test_... for the sandbox, the live key in production). Never in code.
  TERMINAL_AFRICA_URL          default https://sandbox.terminal.africa/v1 -- the SANDBOX. Set https://api.terminal.africa/v1 to go live.
  TERMINAL_CURRENCY            the currency Terminal quotes in (default NGN). Only used when a rate carries no currency of its own.
  TERMINAL_FX_<FROM>_<TO>      how many <TO> one <FROM> is worth, e.g. TERMINAL_FX_NGN_USD=0.00065. Needed when Terminal's currency
                               is not the checkout currency; without it a live quote is refused and checkout uses the flat fee.
  SHIPPING_QUOTE_BUFFER_PERCENT  added to every live quote so a small rate change is not a loss (default 10).
  DEFAULT_WEIGHT_GRAMS         weight assumed for a product with none set (default 500).
  TERMINAL_DECLARED_CURRENCY   currency the item values are declared in (default: the checkout currency).

The flow Terminal documents: create the addresses and parcel (the "quick shipment" call does it in one), ask for rates, pick one,
arrange pickup. A rate is asked for at checkout (quote_unit_shipping) and again, for real, when the seller seals the bag
(TerminalCourier.request_pickup): the cheapest rate then is booked, and Lumin absorbs any difference from the quote.

Unverified against the live service (the sandbox cannot be reached from where this was written): the names of the id and amount
fields in responses, and whether an item's `weight` is per unit or for the whole line. _pick and _rate_amount are the only places
that read response fields; if a sandbox run disagrees, they are what to change.
"""
from app.shippable import product_chargeable_grams
import logging
import os
import time
from decimal import ROUND_UP, Decimal, InvalidOperation

import httpx

from app.phone import to_e164

log = logging.getLogger(__name__)

DEFAULT_WEIGHT_GRAMS = int(os.environ.get("DEFAULT_WEIGHT_GRAMS", "500"))
QUOTE_TTL_SECONDS = 600


def checkout_currency(country: "str | None" = None) -> str:
    """What buyers are charged in: the currency of the country the order is delivered to (app/countries.py); with no country
    (or one with no route) this deployment's single currency (app/payment_provider.py)."""
    from app import countries
    from app.payment_provider import charge_currency

    route = countries.ROUTES.get((country or "").strip().upper())
    return route.currency if route is not None else charge_currency()


class TerminalError(Exception):
    """Terminal said no, could not be reached, or sent something unexpected. The message is safe to log, not to show a buyer."""


def _base_url() -> str:
    return os.environ.get("TERMINAL_AFRICA_URL", "https://sandbox.terminal.africa/v1").rstrip("/")


def _request(method: str, path: str, *, json: "dict | None" = None, params: "dict | None" = None):
    key = os.environ.get("TERMINAL_AFRICA_SECRET_KEY", "")
    if not key:
        raise TerminalError("TERMINAL_AFRICA_SECRET_KEY is not set")
    try:
        resp = httpx.request(
            method,
            f"{_base_url()}{path}",
            json=json,
            params=params,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise TerminalError(f"could not reach Terminal Africa: {exc.__class__.__name__}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400 or (isinstance(body, dict) and body.get("status") is False):
        message = body.get("message") if isinstance(body, dict) else None
        raise TerminalError(f"Terminal Africa {resp.status_code}: {message or 'request failed'}")
    return body.get("data") if isinstance(body, dict) else None


def _pick(data, key: str, prefix: str) -> str:
    """An id out of a response: the named field, which must look like its kind (SH-..., RT-...)."""
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.startswith(prefix):
        raise TerminalError(f"Terminal Africa response has no usable {key}")
    return value


# ---- payloads ----

def address_payload(*, first_name, last_name, email, phone, line1, line2, city, state, country, zip_code, residential=True) -> dict:
    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": to_e164(phone, country),
        "is_residential": residential,
        "line1": line1,
        "line2": line2 or "",
        "city": city,
        "state": state or "",
        "country": country.upper(),
        "zip": zip_code or "",
    }
    if email:
        payload["email"] = email
    return payload


def split_name(full: str) -> "tuple[str, str]":
    parts = (full or "").split(None, 1)
    first = parts[0] if parts else "Customer"
    return first, (parts[1] if len(parts) > 1 else first)  # the API wants both; a single name is used for each


def parcel_payload(*, name: str, value: Decimal, currency: str, weight_grams: "int | None", quantity: int = 1) -> dict:
    grams = weight_grams if weight_grams and weight_grams > 0 else DEFAULT_WEIGHT_GRAMS
    weight_kg = round(grams / 1000, 3)
    return {
        "description": name[:200],
        "weight_unit": "kg",
        "items": [
            {
                "description": name[:200],
                "name": name[:200],
                "currency": currency,
                "value": float(value),
                "quantity": quantity,
                "weight": weight_kg,
            }
        ],
        "metadata": {},
    }


# ---- calls ----

def quick_shipment(pickup: dict, delivery: dict, parcel: dict) -> str:
    """Addresses and parcel in one call -> the shipment id (SH-...)."""
    data = _request("POST", "/shipments/quick", json={"pickup_address": pickup, "delivery_address": delivery, "parcel": parcel})
    return _pick(data, "shipment_id", "SH-")


def get_rates(shipment_id: str) -> "list[dict]":
    data = _request("GET", "/rates/shipment", params={"shipment_id": shipment_id})
    rates = data.get("rates") if isinstance(data, dict) else data
    if not isinstance(rates, list) or not rates:
        raise TerminalError("Terminal Africa has no rates for this route")
    return rates


def _rate_amount(rate: dict) -> Decimal:
    try:
        amount = Decimal(str(rate["amount"]))
    except (KeyError, InvalidOperation):
        raise TerminalError("a Terminal Africa rate has no usable amount") from None
    if amount < 0:
        raise TerminalError("a Terminal Africa rate has a negative amount")
    return amount


def cheapest(rates: "list[dict]") -> dict:
    return min(rates, key=_rate_amount)


def arrange_pickup(shipment_id: str, rate_id: str) -> dict:
    return _request("POST", "/shipments/pickup", json={"shipment_id": shipment_id, "rate_id": rate_id}) or {}


def track(shipment_id: str) -> dict:
    return _request("GET", f"/shipments/track/{shipment_id}") or {}


def cancel(shipment_id: str) -> None:
    _request("POST", "/shipments/cancel", json={"shipment_id": shipment_id})


# ---- webhooks ----

def verify_signature(raw_body: bytes, received: "str | None") -> bool:
    """Terminal signs every webhook: X-Terminal-Signature = hex HMAC-SHA512 of the exact raw request bytes, keyed with the
    account's secret key. False when there is no key, no signature, or it does not match (constant-time compare)."""
    import hashlib
    import hmac

    key = os.environ.get("TERMINAL_AFRICA_SECRET_KEY", "")
    if not key or not isinstance(received, str) or not isinstance(raw_body, (bytes, bytearray)):
        return False
    expected = hmac.new(key.encode("utf-8"), bytes(raw_body), hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, received.strip().lower())


# ---- money ----

def convert(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    if from_currency.upper() == to_currency.upper():
        return amount
    raw = os.environ.get(f"TERMINAL_FX_{from_currency.upper()}_{to_currency.upper()}")
    try:
        factor = Decimal(raw) if raw else None
    except InvalidOperation:
        factor = None
    if factor is None or factor <= 0:
        raise TerminalError(f"no conversion rate set (TERMINAL_FX_{from_currency.upper()}_{to_currency.upper()})")
    return amount * factor


def with_buffer(amount: Decimal) -> Decimal:
    """The buyer's price: the quote plus the buffer, rounded up to the cent."""
    percent = Decimal(os.environ.get("SHIPPING_QUOTE_BUFFER_PERCENT", "10"))
    return (amount * (Decimal(100) + percent) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_UP)


# ---- the checkout quote ----

_quote_cache: "dict[tuple, tuple[float, Decimal]]" = {}


def quote_unit_shipping(pickup: dict, delivery: dict, *, name: str, value: Decimal, weight_grams: "int | None", currency: str) -> Decimal:
    """What one unit of this product costs to ship from the seller to the buyer, in the checkout currency, buffer included.
    Raises TerminalError if it cannot be worked out (the caller falls back to the flat fee). Cached for a few minutes: a quote
    creates a draft shipment at Terminal, and a buyer reopening checkout should not pile them up."""
    grams = weight_grams if weight_grams and weight_grams > 0 else DEFAULT_WEIGHT_GRAMS
    cache_key = (
        tuple(sorted(pickup.items())),
        tuple(sorted(delivery.items())),
        grams,
        currency.upper(),
        str(value),
    )
    hit = _quote_cache.get(cache_key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < QUOTE_TTL_SECONDS:
        return hit[1]
    declared = os.environ.get("TERMINAL_DECLARED_CURRENCY") or currency
    parcel = parcel_payload(name=name, value=value, currency=declared, weight_grams=grams)
    rate = cheapest(get_rates(quick_shipment(pickup, delivery, parcel)))
    price = with_buffer(convert(_rate_amount(rate), str(rate.get("currency") or os.environ.get("TERMINAL_CURRENCY", "NGN")), currency))
    if len(_quote_cache) > 500:
        _quote_cache.clear()
    _quote_cache[cache_key] = (now, price)
    return price


# ---- the courier (app/courier.py picks it with COURIER=terminal) ----

class TerminalCourier:
    """Books the driver through Terminal Africa when the seller seals the bag. The reference kept is Terminal's shipment id."""

    name = "terminal"

    def request_pickup(self, shipment, order) -> "str | None":
        from app.courier import pickup_address_for

        pickup_raw = pickup_address_for(order)
        if pickup_raw is None:
            raise TerminalError("the seller has no pickup address")
        ship_to = order.shipping_address
        if not ship_to:
            raise TerminalError("the order has no delivery address")
        pickup = address_payload(
            first_name=pickup_raw["first_name"],
            last_name=pickup_raw["last_name"],
            email=pickup_raw["email"],
            phone=pickup_raw["phone"],
            line1=pickup_raw["line1"],
            line2=pickup_raw["line2"],
            city=pickup_raw["city"],
            state=pickup_raw["state"],
            country=pickup_raw["country"],
            zip_code=pickup_raw["zip"],
            residential=False,
        )
        first, last = split_name(ship_to.get("recipient_name", ""))
        buyer = getattr(order, "buyer", None)
        delivery = address_payload(
            first_name=first,
            last_name=last,
            email=getattr(buyer, "email", None),
            phone=ship_to["phone"],
            line1=ship_to["line1"],
            line2=ship_to.get("line2"),
            city=ship_to["city"],
            state=ship_to.get("state"),
            country=ship_to["country"],
            zip_code=ship_to.get("postal_code"),
        )
        product = order.product
        parcel = parcel_payload(
            name=order.product_name,
            value=Decimal(str(order.price)),
            currency=os.environ.get("TERMINAL_DECLARED_CURRENCY") or checkout_currency(ship_to.get("country")),
            weight_grams=product_chargeable_grams(product),
        )
        shipment_id = quick_shipment(pickup, delivery, parcel)
        rate = cheapest(get_rates(shipment_id))
        arrange_pickup(shipment_id, _pick(rate, "rate_id", "RT-"))
        return shipment_id
