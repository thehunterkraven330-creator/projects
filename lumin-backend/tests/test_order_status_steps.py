"""A seller may only move an order one step forward by hand (pending -> shipped -> delivered). Anything else is refused, so
"delivered" (which starts the 24-hour countdown to the seller's payout) can't be claimed for an order that was never sent."""
from app.models import MerchantAccount, Order, OrderStatus
from tests.conftest import auth, client, db, make_product, make_user  # noqa: F401  (fixtures)


def _order(db, status):
    seller = make_user(db, "seller")
    merchant = MerchantAccount(user_id=seller.id, business_name="Shop", category="Fashion")
    db.add(merchant)
    db.commit()
    product = make_product(db, merchant_id=merchant.id)
    order = Order(buyer_id=make_user(db, "buyer").id, buyer_name="B", product_id=product.id, product_name="W", price=10, status=status)
    db.add(order)
    db.commit()
    return seller, order


def _set(client, seller, order, status):
    return client.patch(f"/orders/{order.id}/status", json={"status": status}, headers=auth(seller))


def test_pending_cannot_jump_to_delivered(client, db):
    seller, order = _order(db, OrderStatus.pending)
    assert _set(client, seller, order, "delivered").status_code == 409
    db.refresh(order)
    assert order.status == OrderStatus.pending and order.delivered_at is None


def test_the_seller_cannot_move_an_order_forward_at_all(client, db):
    seller, order = _order(db, OrderStatus.pending)
    assert _set(client, seller, order, "shipped").status_code == 409  # the courier does this, never the seller
    db.refresh(order)
    assert order.status == OrderStatus.pending


def test_a_cancelled_order_cannot_be_reopened_or_cancelled_by_hand(client, db):
    seller, order = _order(db, OrderStatus.cancelled)
    assert _set(client, seller, order, "delivered").status_code == 409
    assert _set(client, seller, order, "shipped").status_code == 409
    seller2, pending = _order(db, OrderStatus.pending)
    assert _set(client, seller2, pending, "cancelled").status_code == 409  # cancelling has its own route (with the refund)
