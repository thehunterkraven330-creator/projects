"""A payout the gateway accepted and then bounced: the order is reopened, the seller told, and it is retried as a NEW transfer,
a limited number of times. Also the currency check on a confirmed charge."""
from datetime import datetime, timedelta, timezone

import pytest

from app import escrow
from app.models import MerchantAccount, Notification, Order, OrderStatus, PayoutStatus
from tests.conftest import make_product, make_user


def _paid_order(db, attempts=0, code="TRF_9"):
    seller = make_user(db, "seller")
    merchant = MerchantAccount(user_id=seller.id, business_name="Shop", category="Fashion", paystack_recipient_code="RCP_x")
    db.add(merchant)
    db.commit()
    product = make_product(db, merchant_id=merchant.id)
    order = Order(
        buyer_id=make_user(db, "buyer").id, buyer_name="B", product_id=product.id, product_name="W", price=10,
        status=OrderStatus.delivered, delivered_at=datetime.now(timezone.utc) - timedelta(days=5),
        payout_status=PayoutStatus.released, payout_transfer_code=code, payout_attempts=attempts,
    )
    db.add(order)
    db.commit()
    return seller, order


def test_a_bounced_payout_reopens_the_order_and_tells_the_seller(db):
    seller, order = _paid_order(db)
    assert escrow.payout_failed(db, "TRF_9", "failed") is True
    db.refresh(order)
    assert order.payout_status == PayoutStatus.held and order.payout_transfer_code is None and order.payout_attempts == 1
    assert db.query(Notification).filter(Notification.user_id == seller.id).count() == 1


def test_the_same_failure_twice_only_counts_once(db):
    _, order = _paid_order(db)
    assert escrow.payout_failed(db, "TRF_9") is True
    assert escrow.payout_failed(db, "TRF_9") is False
    db.refresh(order)
    assert order.payout_attempts == 1


def test_an_unknown_transfer_is_ignored(db):
    _paid_order(db)
    assert escrow.payout_failed(db, "TRF_other") is False


def test_a_reopened_order_is_paid_again_on_the_next_sweep(db, monkeypatch):
    _, order = _paid_order(db)
    sent = []
    monkeypatch.setattr(escrow, "pay_seller", lambda merchant, o, amount, reason: sent.append(o.payout_attempts) or "TRF_10")
    escrow.payout_failed(db, "TRF_9")
    db.refresh(order)
    escrow.release_to_merchant(db, order)
    db.refresh(order)
    assert sent == [1] and order.payout_status == PayoutStatus.released and order.payout_transfer_code == "TRF_10"


def test_after_too_many_failures_it_is_left_for_a_person(db, monkeypatch):
    _, order = _paid_order(db, attempts=escrow.MAX_PAYOUT_ATTEMPTS)
    order.payout_status = PayoutStatus.held
    db.commit()
    sent = []
    monkeypatch.setattr(escrow, "pay_seller", lambda *a: sent.append(1) or "T")
    escrow.release_to_merchant(db, order)
    db.refresh(order)
    assert sent == [] and order.payout_status == PayoutStatus.held


@pytest.mark.parametrize("data,ok", [({}, True), ({"currency": "NGN"}, True), ({"currency": "ngn"}, True), ({"currency": "USD"}, False)])
def test_a_charge_in_the_wrong_currency_is_refused(data, ok):
    from app.routers import payments

    assert payments._currency_ok(data) is ok
