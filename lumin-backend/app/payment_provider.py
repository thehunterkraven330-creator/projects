"""Which payment gateway is live. PAYMENT_PROVIDER=stripe (default) or paystack (the old integration, kept working).

Kept in its own tiny module (no imports from the app) so models, routers and escrow can all read it without import loops.
"""
import os

PROVIDER = (os.environ.get("PAYMENT_PROVIDER") or "stripe").strip().lower()
if PROVIDER not in ("stripe", "paystack"):
    raise RuntimeError(f'PAYMENT_PROVIDER must be "stripe" or "paystack", got "{PROVIDER}"')


def is_stripe() -> bool:
    return PROVIDER == "stripe"


def charge_currency() -> str:
    """The currency buyers are charged in, whichever gateway is live. PAYMENT_CURRENCY (PAYSTACK_CURRENCY is the old name).
    Unset: naira with Paystack (its payouts are naira only), dollars with Stripe."""
    return (os.environ.get("PAYMENT_CURRENCY") or os.environ.get("PAYSTACK_CURRENCY") or ("NGN" if PROVIDER == "paystack" else "USD")).strip().upper()


def provider_of(payment) -> str:
    """The gateway that took this payment: the one stored on it, else (a payment from before that was stored) this deployment's."""
    return (getattr(payment, "provider", None) or PROVIDER) if payment is not None else PROVIDER


def currency_of(payment) -> str:
    return ((getattr(payment, "currency", None) or charge_currency()) if payment is not None else charge_currency()).upper()


def merchant_provider(merchant) -> str:
    """How this seller is paid: decided by the country they collect from (app/countries.py). A seller who never said where
    (an old account) uses this deployment's provider."""
    from app import countries

    r = countries.ROUTES.get((getattr(merchant, "pickup_country", None) or "").strip().upper())
    return r.provider if r is not None else PROVIDER
