"""Orders nobody sends are cancelled and refunded on their own: a seller who never taps Ready for pickup (warned first), and a
courier who never collects. NEEDS a Postgres (see conftest); not run in the build sandbox."""
from datetime import datetime, timedelta, timezone

from app import order_cancel
from app.models import MerchantAccount, Notification, Order, OrderStatus, Shipment
from app.models.seal import SHIP_AWAITING, SHIP_IN_TRANSIT
from tests.conftest import client, db, make_product, make_user  # noqa: F401  (fixtures)


def _order(db, age_hours):
    seller = make_user(db, "seller")
    merchant = MerchantAccount(user_id=seller.id, business_name="Shop", category="Fashion")
    db.add(merchant)
    db.commit()
    product = make_product(db, merchant_id=merchant.id)
    order = Order(buyer_id=make_user(db, "buyer").id, buyer_name="B", product_id=product.id, product_name="W", price=10, status=OrderStatus.pending)
    db.add(order)
    db.commit()
    order.created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    db.commit()
    return seller, order


def test_fresh_order_is_left_alone(db):
    _, order = _order(db, 5)
    assert order_cancel.sweep_unfulfilled(db) == {"reminded": 0, "cancelled_unpacked": 0, "cancelled_uncollected": 0}
    db.refresh(order)
    assert order.status == OrderStatus.pending


def test_unpacked_order_gets_one_warning_then_is_cancelled(db):
    seller, order = _order(db, 50)
    assert order_cancel.sweep_unfulfilled(db)["reminded"] == 1
    assert order_cancel.sweep_unfulfilled(db)["reminded"] == 0  # only once
    assert db.query(Notification).filter(Notification.user_id == seller.id).count() == 1
    order.created_at = datetime.now(timezone.utc) - timedelta(hours=73)
    db.commit()
    assert order_cancel.sweep_unfulfilled(db)["cancelled_unpacked"] == 1
    db.refresh(order)
    assert order.status == OrderStatus.cancelled and order.cancel_reason


def test_uncollected_shipment_is_cancelled_but_one_with_a_driver_is_not(db):
    _, waiting = _order(db, 100)
    db.add(Shipment(order_id=waiting.id, bag_id=None, courier="manual", status=SHIP_AWAITING))
    _, moving = _order(db, 100)
    moving.status = OrderStatus.shipped
    db.add(Shipment(order_id=moving.id, bag_id=None, courier="manual", status=SHIP_IN_TRANSIT))
    db.commit()
    for sh in db.query(Shipment).all():
        sh.created_at = datetime.now(timezone.utc) - timedelta(hours=80)
    db.commit()
    assert order_cancel.sweep_unfulfilled(db)["cancelled_uncollected"] == 1
    db.refresh(waiting); db.refresh(moving)
    assert waiting.status == OrderStatus.cancelled and moving.status == OrderStatus.shipped
