"""`python -m app.seed --test-order EMAIL`: a test order on the seller's own account for trying the live-test and sealing flow.
Nothing real may happen for it: no payout, no refund, no courier booking."""
import pytest

from app import gateway, seed, shipments
from app.models import MerchantAccount, Order, Payment, PaymentStatus
from tests.conftest import make_product, make_user


def _seller_with_product(db):
    u = make_user(db, "tester")
    m = MerchantAccount(user_id=u.id, business_name="Test Shop", category="Fashion", pickup_country="NG")
    db.add(m)
    db.commit()
    p = make_product(db, merchant_id=m.id)
    return u, m, p


def test_it_creates_a_pending_order_on_the_sellers_product(db):
    u, m, p = _seller_with_product(db)
    seed.run_test_order(u.email)
    db.expire_all()
    pay = db.query(Payment).filter(Payment.reference.like("test-order-%")).one()
    assert pay.status == PaymentStatus.success and pay.provider == "paystack" and pay.currency == "NGN"
    order = db.query(Order).filter_by(payment_id=pay.id).one()
    assert order.product_id == p.id and order.buyer_name == "Test Buyer"


def test_it_does_nothing_for_someone_who_is_not_a_seller_or_has_no_product(db, capsys):
    u = make_user(db, "plain")
    seed.run_test_order(u.email)
    assert "No seller account" in capsys.readouterr().out
    m = MerchantAccount(user_id=u.id, business_name="Empty", category="Fashion")
    db.add(m)
    db.commit()
    seed.run_test_order(u.email)
    assert "no product in stock" in capsys.readouterr().out
    assert db.query(Payment).count() == 0


def test_no_real_gateway_is_touched_for_a_test_order(db, monkeypatch):
    u, m, p = _seller_with_product(db)
    seed.run_test_order(u.email)
    order = db.query(Order).filter_by(product_id=p.id).one()

    def boom(*a, **k):
        raise AssertionError("a real gateway was called for a test order")

    monkeypatch.setattr(gateway, "_impl_module", boom)
    assert gateway.pay_seller(m, order, 1000, "x").startswith("test-transfer-")
    assert gateway.refund_transaction(order.payment.reference, 1000, order.id, provider="paystack") == {"test_order": True}


def test_removing_test_orders_puts_the_stock_back(db):
    u, m, p = _seller_with_product(db)
    p.stock_quantity = 5
    db.commit()
    seed.run_test_order(u.email)
    db.expire_all()
    assert db.get(type(p), p.id).stock_quantity == 4
    seed.remove_test_orders(u.email)
    db.expire_all()
    assert db.get(type(p), p.id).stock_quantity == 5
    assert db.query(Order).count() == 0 and db.query(Payment).count() == 0


def test_running_it_again_does_not_add_a_second_test_order(db, capsys):
    u, m, p = _seller_with_product(db)
    seed.run_test_order(u.email)
    seed.run_test_order(u.email)  # every deploy while TEST_ORDER_FOR is set
    assert "already has a test order" in capsys.readouterr().out
    assert db.query(Order).count() == 1
