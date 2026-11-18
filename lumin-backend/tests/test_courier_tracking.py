"""An order WITHOUT a live test is moved by its courier: "Ready for pickup" books a driver, the courier's pickup event makes it
shipped, its delivered event makes it delivered (and starts the claim window). With a courier connected the seller can no
longer set shipped / delivered by hand. NEEDS a Postgres (see conftest); not run in the build sandbox."""
from app import shipments
from app.models import MerchantAccount, Order, OrderStatus, Shipment
from app.models.seal import SHIP_AWAITING, SHIP_DELIVERED, SHIP_IN_TRANSIT
from tests.conftest import auth, client, db, make_product, make_user  # noqa: F401  (fixtures)


def _order(db, status=OrderStatus.pending):
    seller = make_user(db, "seller")
    merchant = MerchantAccount(
        user_id=seller.id, business_name="Shop", category="Fashion",
        pickup_contact_name="Ada Obi", pickup_phone="+2348000000000", pickup_line1="1 Main St", pickup_city="Lagos",
        pickup_state="Lagos", pickup_country="NG",
    )
    db.add(merchant)
    db.commit()
    product = make_product(db, merchant_id=merchant.id)
    order = Order(buyer_id=make_user(db, "buyer").id, buyer_name="B", product_id=product.id, product_name="W", price=10, status=status)
    db.add(order)
    db.commit()
    return seller, order


class _FakeCourier:
    name = "terminal"

    def request_pickup(self, shipment, order):
        return "SH-123"


def _with_courier(monkeypatch):
    monkeypatch.setenv("COURIER", "terminal")
    monkeypatch.setattr("app.courier.get_courier", lambda: _FakeCourier())


def _event(name):
    return {"event": name, "data": {"shipment": "SH-123"}}


def test_ready_for_pickup_then_courier_events_move_the_order(client, db, monkeypatch):
    _with_courier(monkeypatch)
    seller, order = _order(db)
    assert client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller)).status_code == 200
    ship = db.query(Shipment).filter(Shipment.order_id == order.id).one()
    assert ship.bag_id is None and ship.status == SHIP_AWAITING and ship.courier_ref == "SH-123"

    assert shipments.handle_terminal_event(db, _event("shipment.in-transit")) == "picked_up"
    db.refresh(order); db.refresh(ship)
    assert order.status == OrderStatus.shipped and ship.status == SHIP_IN_TRANSIT

    assert shipments.handle_terminal_event(db, _event("shipment.delivered")) == "delivered"
    db.refresh(order); db.refresh(ship)
    assert order.status == OrderStatus.delivered and order.delivered_at is not None and ship.status == SHIP_DELIVERED
    # a repeated webhook changes nothing
    assert shipments.handle_terminal_event(db, _event("shipment.delivered")) == "ignored"


def test_delivered_before_pickup_is_ignored(client, db, monkeypatch):
    _with_courier(monkeypatch)
    seller, order = _order(db)
    client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller))
    assert shipments.handle_terminal_event(db, _event("shipment.delivered")) == "ignored"
    db.refresh(order)
    assert order.status == OrderStatus.pending


def test_seller_can_never_set_shipped_or_delivered_by_hand(client, db, monkeypatch):
    for courier_name in ("terminal", "manual"):
        monkeypatch.setenv("COURIER", courier_name)
        seller, order = _order(db)
        for st in ("shipped", "delivered"):
            assert client.patch(f"/orders/{order.id}/status", json={"status": st}, headers=auth(seller)).status_code == 409
        db.refresh(order)
        assert order.status == OrderStatus.pending


def test_manual_courier_admin_marks_pickup_and_delivery(client, db, monkeypatch):
    monkeypatch.setenv("COURIER", "manual")
    seller, order = _order(db)
    assert client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller)).status_code == 200
    ship = db.query(Shipment).filter(Shipment.order_id == order.id).one()
    assert shipments.mark_courier_delivered(db, ship.id) is False  # not collected yet
    shipments.mark_picked_up(db, ship.id, None)
    assert shipments.mark_courier_delivered(db, ship.id) is True
    db.refresh(order)
    assert order.status == OrderStatus.delivered and order.delivered_at is not None


def test_cancel_before_pickup_closes_the_shipment(client, db, monkeypatch):
    _with_courier(monkeypatch)
    seller, order = _order(db)
    client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller))
    shipments.on_order_cancelled(db, order)  # no bag: must not touch seal_bags
    db.commit()
    assert db.query(Shipment).filter(Shipment.order_id == order.id).one().status != SHIP_AWAITING


def test_delivered_without_an_in_transit_event_still_delivers(client, db, monkeypatch):
    _with_courier(monkeypatch)
    seller, order = _order(db)
    client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller))
    assert shipments.handle_terminal_event(db, _event("shipment.delivered")) == "delivered"
    db.refresh(order)
    assert order.status == OrderStatus.delivered


def test_admin_can_deliver_an_order_a_seller_marked_shipped_long_ago(client, db):
    _, order = _order(db, OrderStatus.shipped)
    assert [o.id for o in shipments.stuck_shipped_orders(db)] == [order.id]
    assert shipments.deliver_stuck_order(db, order.id) is True
    db.refresh(order)
    assert order.status == OrderStatus.delivered and order.delivered_at is not None
    assert shipments.stuck_shipped_orders(db) == []
