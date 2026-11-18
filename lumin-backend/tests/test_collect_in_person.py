"""Collect in person (machines and bulk goods): details sent by the seller, then the buyer accepts (paid) or rejects (refunded).
NEEDS a Postgres (see conftest); not run in the build sandbox."""
from datetime import datetime, timedelta, timezone

from app import order_cancel
from app.models import MerchantAccount, Order, OrderStatus
from tests.conftest import auth, client, db, make_product, make_user  # noqa: F401  (fixtures)


def _setup(db):
    seller = make_user(db, "seller")
    merchant = MerchantAccount(
        user_id=seller.id, business_name="Shop", category="Machines", pickup_contact_name="Tunde Ade", pickup_phone="+2348000000000",
        pickup_line1="12 Yard Rd", pickup_city="Lagos", pickup_state="Lagos", pickup_postal_code="100001", pickup_country="NG",
    )
    db.add(merchant)
    db.commit()
    product = make_product(db, merchant_id=merchant.id)
    product.collect_in_person = True
    buyer = make_user(db, "buyer")
    order = Order(buyer_id=buyer.id, buyer_name="B", product_id=product.id, product_name="Lathe", price=500,
                  status=OrderStatus.pending, collect_in_person=True)
    db.add(order)
    db.commit()
    return seller, buyer, order


def _coming(hours=48):
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    return {"when": when.isoformat(), "when_label": "Sat 10:00"}


def test_the_buyer_is_shown_the_sellers_saved_address_and_deadline(client, db):
    seller, buyer, order = _setup(db)
    assert order.collect_address == "12 Yard Rd, Lagos, Lagos, 100001, NG"
    assert order.collect_contact_name == "Tunde Ade" and order.collect_phone == "+2348000000000"
    assert order.collect_deadline is not None and order.collect_deadline > datetime.now(timezone.utc)


def test_coming_tells_the_seller_and_must_be_inside_the_window(client, db):
    seller, buyer, order = _setup(db)
    assert client.post(f"/orders/{order.id}/coming", json=_coming(), headers=auth(buyer)).status_code == 200
    assert client.post(f"/orders/{order.id}/coming", json=_coming(hours=-2), headers=auth(buyer)).status_code == 422
    assert client.post(f"/orders/{order.id}/coming", json=_coming(hours=24 * 30), headers=auth(buyer)).status_code == 422
    assert client.post(f"/orders/{order.id}/coming", json=_coming(), headers=auth(seller)).status_code == 404  # only the buyer


def test_accept_delivers_the_order_and_only_the_buyer_can(client, db):
    seller, buyer, order = _setup(db)
    assert client.post(f"/orders/{order.id}/collect-accept", headers=auth(seller)).status_code == 404
    assert client.post(f"/orders/{order.id}/collect-accept", headers=auth(buyer)).status_code == 200
    db.refresh(order)
    assert order.status == OrderStatus.delivered and order.delivered_at is not None


def test_a_collect_product_needs_a_pickup_address(client, db):
    seller, _, _ = _setup(db)
    seller.merchant_account.pickup_line1 = None
    db.commit()
    r = client.post("/merchant/products", json={"name": "Lathe", "price": 500, "description": "d", "image_urls": ["https://x/i.jpg"], "collect_in_person": True}, headers=auth(seller))
    assert r.status_code == 409


def test_reject_refunds_and_cancels(client, db):
    seller, buyer, order = _setup(db)
    assert client.post(f"/orders/{order.id}/collect-reject", json={"code": "other", "reason": ""}, headers=auth(buyer)).status_code == 422
    assert client.post(f"/orders/{order.id}/collect-reject", json={"code": "not_as_described", "reason": "Not the model shown"}, headers=auth(buyer)).status_code == 200
    db.refresh(order)
    assert order.status == OrderStatus.cancelled and "Not the model" in order.cancel_reason


def test_collect_orders_have_no_courier_and_no_defect_claim(client, db):
    seller, buyer, order = _setup(db)
    assert client.post(f"/orders/{order.id}/ready-for-pickup", headers=auth(seller)).status_code == 409
    order.status = OrderStatus.delivered
    order.delivered_at = datetime.now(timezone.utc)
    db.commit()
    r = client.post(f"/orders/{order.id}/report-defect", json={"reason": "broken", "video_url": "https://x/v.mp4"}, headers=auth(buyer))
    assert r.status_code == 409


def test_buyer_is_reminded_then_refunded_when_the_window_ends(db):
    _, buyer, order = _setup(db)
    order.created_at = datetime.now(timezone.utc) - timedelta(days=6, hours=2)
    db.commit()
    assert order_cancel.sweep_unfulfilled(db)["reminded"] == 1
    assert order_cancel.sweep_unfulfilled(db)["reminded"] == 0  # once
    order.created_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    assert order_cancel.sweep_unfulfilled(db)["cancelled_uncollected"] == 1
    db.refresh(order)
    assert order.status == OrderStatus.cancelled


def test_the_seller_is_never_chased_to_pack_a_collect_order(db):
    _, _, order = _setup(db)
    order.created_at = datetime.now(timezone.utc) - timedelta(hours=60)
    db.commit()
    assert order_cancel.sweep_unfulfilled(db) == {"reminded": 0, "cancelled_unpacked": 0, "cancelled_uncollected": 0}


def test_a_heavy_product_is_collect_in_person_whatever_the_seller_ticked(client, db):
    seller, _, _ = _setup(db)
    body = {"name": "Press", "price": 900, "description": "d", "image_urls": ["https://x/i.jpg"], "weight_grams": 60_000, "collect_in_person": False}
    r = client.post("/merchant/products", json=body, headers=auth(seller))
    assert r.status_code in (200, 201) and r.json()["collect_in_person"] is True
    seller.merchant_account.pickup_line1 = None
    db.commit()
    assert client.post("/merchant/products", json=body, headers=auth(seller)).status_code == 409  # nowhere to collect from


def test_a_light_product_is_not_forced(client, db):
    from app.shippable import too_heavy_to_post

    assert too_heavy_to_post(29_999) is False and too_heavy_to_post(30_001) is True and too_heavy_to_post(None) is False


def test_size_counts_as_weight(client, db):
    seller, _, _ = _setup(db)
    big_light = {"name": "Crate", "price": 100, "description": "d", "image_urls": ["https://x/i.jpg"], "weight_grams": 2000,
                 "length_cm": 100, "width_cm": 100, "height_cm": 100}
    r = client.post("/merchant/products", json=big_light, headers=auth(seller))
    assert r.status_code in (200, 201) and r.json()["collect_in_person"] is True  # 1 m3 counts as 200 kg
    heavy_no_size = {"name": "Box", "price": 100, "description": "d", "image_urls": ["https://x/i.jpg"], "weight_grams": 8000}
    assert client.post("/merchant/products", json=heavy_no_size, headers=auth(seller)).status_code == 422  # over 5 kg: say the size
    ok = {**heavy_no_size, "length_cm": 30, "width_cm": 20, "height_cm": 20}
    r = client.post("/merchant/products", json=ok, headers=auth(seller))
    assert r.status_code in (200, 201) and r.json()["collect_in_person"] is False


def test_an_order_with_no_payment_is_its_own_group(client, db):
    from app.routers.orders import _collect_group

    _, _, first = _setup(db)
    assert [o.id for o in _collect_group(db, first)] == [first.id]


def _photo(monkeypatch):
    monkeypatch.setattr("app.storage.key_from_view_url", lambda url: "k" if url and url.startswith("https://cdn.test/") else None)
    return "https://cdn.test/place.jpg"


def test_no_show_needs_a_planned_time_that_has_passed_and_a_photo(client, db, monkeypatch):
    seller, buyer, order = _setup(db)
    photo = _photo(monkeypatch)
    body = {"code": "seller_not_there", "reason": "", "photo_url": photo}
    assert client.post(f"/orders/{order.id}/collect-reject", json=body, headers=auth(buyer)).status_code == 409  # never said when
    order.visit_details_at = datetime.now(timezone.utc) + timedelta(hours=5)
    db.commit()
    assert client.post(f"/orders/{order.id}/collect-reject", json=body, headers=auth(buyer)).status_code == 409  # not yet time
    order.visit_details_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    no_photo = {"code": "seller_not_there", "reason": ""}
    assert client.post(f"/orders/{order.id}/collect-reject", json=no_photo, headers=auth(buyer)).status_code == 422
    assert client.post(f"/orders/{order.id}/collect-reject", json={**body, "photo_url": "https://elsewhere/x.jpg"}, headers=auth(buyer)).status_code == 422
    assert client.post(f"/orders/{order.id}/collect-reject", json=body, headers=auth(buyer)).status_code == 200
    db.refresh(order)
    assert order.status == OrderStatus.cancelled


def test_a_claim_is_not_a_strike_until_an_admin_confirms(client, db, monkeypatch):
    from app.models import CollectNoShow
    from app.routers.collect_admin import _decide
    from app.models.collect import NOSHOW_CONFIRMED

    seller, buyer, order = _setup(db)
    photo = _photo(monkeypatch)
    order.visit_details_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    client.post(f"/orders/{order.id}/collect-reject", json={"code": "seller_not_there", "reason": "", "photo_url": photo}, headers=auth(buyer))
    db.refresh(seller.merchant_account)
    assert seller.merchant_account.collect_no_show_strikes == 0
    claim = db.query(CollectNoShow).one()
    # the seller answers
    assert client.post(f"/orders/{order.id}/noshow-reply", json={"note": "I was there all day", "photo_url": photo}, headers=auth(seller)).status_code == 200
    assert client.post(f"/orders/{order.id}/noshow-reply", json={"note": "x"}, headers=auth(buyer)).status_code in (404, 422)
    _decide(db, claim.id, NOSHOW_CONFIRMED)
    db.refresh(seller.merchant_account)
    assert seller.merchant_account.collect_no_show_strikes == 1


def test_other_reasons_need_words_and_give_no_strike(client, db):
    from app.routers.collect_admin import outcome_of

    seller, buyer, order = _setup(db)
    assert client.post(f"/orders/{order.id}/collect-reject", json={"code": "other", "reason": ""}, headers=auth(buyer)).status_code == 422
    r = client.post(f"/orders/{order.id}/collect-reject", json={"code": "not_as_described", "reason": "Wrong model"}, headers=auth(buyer))
    assert r.status_code == 200
    db.refresh(order); db.refresh(seller.merchant_account)
    assert outcome_of(order) == "rejected" and seller.merchant_account.collect_no_show_strikes == 0


def test_seller_refused_is_a_claim_like_no_show_but_needs_words(client, db, monkeypatch):
    from app.models import CollectNoShow
    from app.routers.collect_admin import outcome_of

    seller, buyer, order = _setup(db)
    photo = _photo(monkeypatch)
    order.visit_details_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert client.post(f"/orders/{order.id}/collect-reject", json={"code": "seller_refused", "reason": "", "photo_url": photo}, headers=auth(buyer)).status_code == 422
    r = client.post(f"/orders/{order.id}/collect-reject", json={"code": "seller_refused", "reason": "He said he had sold it", "photo_url": photo}, headers=auth(buyer))
    assert r.status_code == 200
    db.refresh(order); db.refresh(seller.merchant_account)
    assert outcome_of(order) == "seller_refused" and seller.merchant_account.collect_no_show_strikes == 0
    assert db.query(CollectNoShow).one().kind == "refused"
