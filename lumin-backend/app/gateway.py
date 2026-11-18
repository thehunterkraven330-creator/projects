"""One door to whichever payment gateway is live (app/payment_provider.py), so payments, escrow and order cancellation do
not care whether it is Stripe or Paystack. Both modules keep the same shapes:

  verify_transaction(reference) -> {"status": "success"|..., "amount": <smallest unit>}
  refund_transaction(reference, amount_subunit, order_id)
  seller_ready(merchant)            can this seller be paid right now?
  pay_seller(merchant, order, amount_subunit, reason) -> transfer code
"""
from app import payment_provider


# A test order (python -m app.seed --test-order, for trying the seller's live-test and sealing flow) has a payment reference that
# starts with this. Nothing was ever charged for it, so nothing may be paid out or refunded through a real gateway for it.
TEST_REFERENCE_PREFIX = "test-order-"


def is_test_reference(reference: str | None) -> bool:
    return bool(reference) and str(reference).startswith(TEST_REFERENCE_PREFIX)


def _impl_module(provider: str | None = None):
    """Chosen at call time (not import time) so tests can flip the provider. `provider` is the one stored on the payment (or
    worked out from the seller's country); None means this deployment's single provider, as before there were several."""
    if (provider or payment_provider.PROVIDER) == "stripe":
        from app import stripe_gateway as impl
    else:
        from app import paystack as impl
    return impl


def verify_transaction(reference: str, provider: str | None = None) -> dict:
    return _impl_module(provider).verify_transaction(reference)


def refund_transaction(reference: str, amount_subunit: int | None = None, order_id=None, provider: str | None = None) -> dict:
    if is_test_reference(reference):
        return {"test_order": True}  # nothing was charged, so nothing to give back
    if (provider or payment_provider.PROVIDER) == "stripe":
        return _impl_module(provider).refund_transaction(reference, amount_subunit, str(order_id) if order_id is not None else None)
    return _impl_module(provider).refund_transaction(reference, amount_subunit)


def seller_ready(db, merchant) -> bool:
    """Stripe: the seller finished Stripe's onboarding and can receive transfers. Paystack: bank details were added.
    For Stripe the answer is cached on the merchant (updated by the account.updated webhook); when the cache says "not yet"
    Stripe is asked once, so a seller who just finished onboarding is paid without waiting for the webhook."""
    if payment_provider.merchant_provider(merchant) != "stripe":
        return merchant.paystack_recipient_code is not None
    if not merchant.stripe_account_id:
        return False
    if merchant.stripe_ready:
        return True
    st = _impl_module("stripe").account_status(merchant.stripe_account_id)
    if st["ready"]:
        merchant.stripe_ready = True
        db.commit()
    return bool(st["ready"])


def pay_seller(merchant, order, amount_subunit: int, reason: str) -> str | None:
    from fastapi import HTTPException

    seller_provider = payment_provider.merchant_provider(merchant)
    payment = getattr(order, "payment", None)
    if payment is not None and is_test_reference(getattr(payment, "reference", None)):
        return f"test-transfer-{order.id}"  # no real transfer for a test order
    charged_by = payment_provider.provider_of(payment)
    if payment is not None and charged_by != seller_provider:
        # Money taken by one gateway cannot be paid out by another. Orders are domestic so this should not happen; refuse
        # rather than move money from a balance that does not hold it.
        raise HTTPException(
            status_code=409, detail=f"This order was paid through {charged_by} but the seller is paid through {seller_provider}"
        )
    if seller_provider == "stripe":
        ref = order.payment.reference if order.payment is not None else None
        if not ref:
            raise HTTPException(status_code=400, detail="No payment on record for this order")
        return _impl_module("stripe").create_transfer(merchant.stripe_account_id, amount_subunit, reason, ref, str(order.id)).get("transfer_code")
    impl = _impl_module("paystack")
    return impl.create_transfer(
        recipient_code=merchant.paystack_recipient_code,
        amount_subunit=amount_subunit,
        reason=reason,
        reference=impl.transfer_reference(order.id, getattr(order, "payout_attempts", 0) or 0),
    ).get("transfer_code")
