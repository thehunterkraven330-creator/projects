import os

import httpx
from fastapi import HTTPException

# Same required-at-startup convention as DATABASE_URL (database.py) and
# JWT_SECRET_KEY (auth/security.py) — fails loudly on boot if unset,
# rather than on the first person to try to pay or the first order
# anyone tries to cancel. Exported (not underscore-prefixed) so
# routers/payments.py can reuse the exact same key for its webhook's
# HMAC signature check, rather than reading the env var a second time.
# Required when any switched-on country is paid through Paystack: app/main.py refuses to start without it (see app/countries.py).
# The module loads regardless (other files import from it) and is only called for Paystack countries.
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
PAYSTACK_BASE_URL = "https://api.paystack.co"

_HEADERS = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}


def verify_transaction(reference: str) -> dict:
    """GET /transaction/verify/:reference — confirms a charge actually
    succeeded (and for how much) against Paystack's own records, rather
    than trusting either the browser's callback or a webhook body.
    Used by /payments/verify and the webhook alike (routers/payments.py).
    """
    try:
        resp = httpx.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=_HEADERS,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Paystack verification failed")
    return resp.json()["data"]


def refund_transaction(reference: str, amount_subunit: int | None = None) -> dict:
    """POST /refund — issues a refund against an already-successful
    charge. `amount_subunit` omitted refunds the full original charge;
    passed issues a partial refund instead. routers/orders.py's
    cancel_order always passes a partial amount, since one Payment can
    fund several Order rows (a cart checkout) and cancelling one
    shouldn't refund the others' share along with it.
    """
    payload: dict = {"transaction": reference}
    if amount_subunit is not None:
        payload["amount"] = amount_subunit

    try:
        resp = httpx.post(
            f"{PAYSTACK_BASE_URL}/refund",
            headers=_HEADERS,
            json=payload,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Paystack refund failed")
    return resp.json()["data"]


def list_banks() -> list[dict]:
    """GET /bank — every bank Paystack knows how to transfer to. Backs
    GET /merchant/banks (routers/merchant.py), which the payout-setup UI
    uses to show real bank names in a picker instead of asking a
    merchant to somehow already know Paystack's own numeric bank_code
    for their bank.
    """
    try:
        resp = httpx.get(f"{PAYSTACK_BASE_URL}/bank", headers=_HEADERS, timeout=15.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not load the bank list from Paystack")
    return resp.json()["data"]


def resolve_account(account_number: str, bank_code: str) -> dict:
    """GET /bank/resolve — looks up the real registered name behind an
    account number+bank code, straight from Paystack/the bank itself.
    Called by POST /merchant/payout (routers/merchant.py) BEFORE
    create_transfer_recipient below, so a merchant's payout details are
    confirmed to belong to a real account before this app ever sends
    money to it, rather than trusting whatever name they might type in.
    """
    try:
        resp = httpx.get(
            f"{PAYSTACK_BASE_URL}/bank/resolve",
            headers=_HEADERS,
            params={"account_number": account_number, "bank_code": bank_code},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400, detail="Couldn't verify that account number against this bank"
        )
    return resp.json()["data"]


def create_transfer_recipient(account_number: str, bank_code: str, name: str) -> dict:
    """POST /transferrecipient — done once per merchant, the moment they
    add or change their payout bank details (routers/merchant.py), not
    per payout. Returns Paystack's own recipient_code, saved onto
    MerchantAccount.paystack_recipient_code and reused for every future
    transfer to them.

    `currency: "NGN"` isn't a display default the way PAYSTACK_CURRENCY
    in payments.py is — Paystack Transfers are NGN-only on a standard
    (non-multi-currency) integration, full stop. That's a real mismatch
    against this app's USD-by-default charges: a deployment actually
    paying merchants out in NGN against USD-denominated orders needs a
    currency conversion step this app doesn't have. Noted here rather
    than silently assumed away — see the same note on create_transfer
    below.
    """
    payload = {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN",
    }
    try:
        resp = httpx.post(
            f"{PAYSTACK_BASE_URL}/transferrecipient",
            headers=_HEADERS,
            json=payload,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Paystack rejected these bank details")
    return resp.json()["data"]


# What Paystack's transfer status means for us. "otp": it is waiting for a person to type a code in the dashboard, so the money is
# NOT moving (the cure is Settings > Preferences > turn off "Confirm transfers before sending"). The rest of the first list means
# it is on its way; transfer.failed / transfer.reversed webhooks tell us later if it bounces (routers/payments.py).
_TRANSFER_OK = {"success", "pending", "received", "queued", "processing"}


def transfer_reference(order_id, attempt: int = 0) -> str:
    """Our own reference for a payout (Paystack allows lowercase letters, digits, - and _, 16 to 50 characters): the same order and
    attempt always give the same one, so a retried call after a timeout can't pay twice; a bounced payout is attempt + 1."""
    return f"lumin-po-{order_id}" + (f"-{attempt}" if attempt else "")


def _check_transfer(data: dict) -> dict:
    status = str(data.get("status") or "").lower()
    if status == "otp":
        raise HTTPException(
            status_code=502,
            detail="Paystack is waiting for a confirmation code before it sends this payout. Turn off transfer confirmation in the Paystack dashboard.",
        )
    if status and status not in _TRANSFER_OK:
        raise HTTPException(status_code=502, detail=f"Paystack did not send this payout ({status})")
    return data


def create_transfer(recipient_code: str, amount_subunit: int, reason: str, reference: str | None = None) -> dict:
    """POST /transfer — the actual escrow release (app/escrow.py's
    release_to_merchant). `source: "balance"` pays out of the platform's
    own Paystack balance (so that balance must hold the money: see
    LAUNCH.md on the settlement schedule), not out of the buyer's
    original charge directly.

    Always in naira (a standard Paystack account can only transfer in NGN), which is why the app refuses to start with Paystack in
    any other charge currency (main.py). `reference` makes the call safe to repeat: a second call with a reference Paystack
    already knows returns that transfer instead of sending another.
    """
    payload = {
        "source": "balance",
        "amount": amount_subunit,
        "recipient": recipient_code,
        "reason": reason,
        "currency": "NGN",
    }
    if reference:
        payload["reference"] = reference
    try:
        resp = httpx.post(
            f"{PAYSTACK_BASE_URL}/transfer",
            headers=_HEADERS,
            json=payload,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Paystack") from exc

    if resp.status_code in (200, 201):
        return _check_transfer(resp.json()["data"])
    if reference:
        # Maybe this very payout was already sent (an earlier call timed out after Paystack took it): ask, and do not send again.
        known = _transfer_by_reference(reference)
        if known is not None:
            return _check_transfer(known)
    raise HTTPException(status_code=502, detail="Paystack transfer failed")


def _transfer_by_reference(reference: str) -> dict | None:
    try:
        resp = httpx.get(f"{PAYSTACK_BASE_URL}/transfer/verify/{reference}", headers=_HEADERS, timeout=15.0)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json().get("data")
    except ValueError:
        return None
