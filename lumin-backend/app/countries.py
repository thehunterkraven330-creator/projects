"""Which payment provider and currency each country uses: the one place that says it.

A seller's country (where they collect parcels from) decides how they are paid; an order is domestic (see app/market.py), so the
buyer is charged by the same provider, in the same currency, in that country. Nothing else in the app reads a global provider
for new orders; rows made before this existed (no provider on the payment) fall back to PAYMENT_PROVIDER (app/payment_provider.py).

Kept free of app imports so schemas, models and routers can all use it.

  LAUNCH_COUNTRIES   comma-separated two-letter codes that are switched ON. Unset = wave 1 (WAVE_1 below). A code that is not in
                     ROUTES is ignored (no provider can pay there yet).

Routes marked `unverified` are listed so they can be turned on, but they are refused at startup unless ALLOW_UNVERIFIED_ROUTES=true:
the code pays Paystack sellers out in naira only (app/paystack.py), so Ghana, Kenya and South Africa need their own payout
handling checked with Paystack first.

Sources for who can be paid: Stripe Connect cross-border payouts (US platform to US, UK, EEA, Canada, Switzerland) and Paystack
(businesses registered in Nigeria, Ghana, South Africa, Kenya). See the design doc "Lumin multi-country payments design".
"""
import os
from typing import NamedTuple


class Route(NamedTuple):
    provider: str  # "stripe" | "paystack"
    currency: str
    unverified: bool = False


ROUTES: dict[str, Route] = {
    # Paystack
    "NG": Route("paystack", "NGN"),
    "GH": Route("paystack", "GHS", unverified=True),
    "KE": Route("paystack", "KES", unverified=True),
    "ZA": Route("paystack", "ZAR", unverified=True),
    # Stripe
    "US": Route("stripe", "USD"),
    "GB": Route("stripe", "GBP"),
    "CA": Route("stripe", "CAD", unverified=True),
    "CH": Route("stripe", "CHF", unverified=True),
}
for _eea in ("AT", "BE", "DE", "ES", "FI", "FR", "IE", "IT", "NL", "PT"):
    ROUTES[_eea] = Route("stripe", "EUR", unverified=True)

WAVE_1 = ["NG", "US", "GB"]


def enabled_countries() -> list[str]:
    raw = os.environ.get("LAUNCH_COUNTRIES")
    codes = WAVE_1 if raw is None or not raw.strip() else [c.strip().upper() for c in raw.split(",") if c.strip()]
    return [c for c in codes if c in ROUTES]


def allow_unverified() -> bool:
    return os.environ.get("ALLOW_UNVERIFIED_ROUTES", "").lower() == "true" or os.environ.get("ALLOW_PAYSTACK_NON_NGN", "").lower() == "true"


def route_for(country: str | None) -> Route | None:
    """The route for an ENABLED country, else None."""
    c = (country or "").strip().upper()
    return ROUTES.get(c) if c in enabled_countries() else None


def providers_in_use() -> set[str]:
    return {ROUTES[c].provider for c in enabled_countries()}


def unverified_enabled() -> list[str]:
    return [c for c in enabled_countries() if ROUTES[c].unverified]
