"""The seller's pickup address: collected at registration, editable, required before sealing, and shaped for the courier API."""
from types import SimpleNamespace as NS

import pytest

from app import courier, seals
from app.models import MerchantAccount, Order, OrderStatus
from tests.conftest import auth, make_product, make_user

ADDRESS = {
    "contact_name": "Ada Obi",
    "phone": "+234 803 123 4567",
    "line1": "12 Allen Avenue",
    "line2": "Opposite the pharmacy",
    "city": "Ikeja",
    "state": "Lagos",
    "postal_code": "100271",
    "country": "ng",
}


def _create(client, user, **over):
    body = {"business_name": "Ada Wears", "category": "Fashion & Apparel", "description": "", "pickup_address": {**ADDRESS, **over}}
    return client.post("/merchant", json=body, headers=auth(user))


def test_registering_stores_the_pickup_address_and_returns_it(client, db):
    user = make_user(db, "ada")
    r = _create(client, user)
    assert r.status_code == 201, r.text
    got = r.json()["pickup_address"]
    assert got["line1"] == "12 Allen Avenue" and got["state"] == "Lagos"
    assert got["country"] == "NG"  # a country code is stored upper-case
    assert client.get("/merchant/me", headers=auth(user)).json()["pickup_address"]["contact_name"] == "Ada Obi"


def test_registering_without_a_pickup_address_is_refused(client, db):
    user = make_user(db, "ada")
    r = client.post("/merchant", json={"business_name": "Ada Wears", "category": "Fashion & Apparel"}, headers=auth(user))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [("contact_name", "  "), ("phone", "12"), ("line1", ""), ("city", ""), ("state", ""), ("country", "Nigeria"), ("country", ""), ("postal_code", ""), ("phone", "0801")],
)
def test_an_incomplete_pickup_address_is_refused(client, db, field, value):
    r = _create(client, make_user(db, "ada"), **{field: value})
    assert r.status_code == 422


def test_the_phone_is_saved_in_international_form(client, db):
    r = _create(client, make_user(db, "ada"), phone="0803 123 4567")
    assert r.status_code in (200, 201)
    assert r.json()["pickup_address"]["phone"] == "+2348031234567"


def test_the_address_can_be_changed_later(client, db):
    user = make_user(db, "ada")
    _create(client, user)
    r = client.patch("/merchant/account", json={"pickup_address": {**ADDRESS, "line1": "5 Marina Road", "line2": None}}, headers=auth(user))
    assert r.status_code == 200, r.text
    assert r.json()["pickup_address"]["line1"] == "5 Marina Road"
    assert r.json()["pickup_address"]["line2"] is None


def test_a_seller_without_an_address_reads_null(client, db):
    user = make_user(db, "old")
    db.add(MerchantAccount(user_id=user.id, business_name="Old Shop", category="Fashion"))
    db.commit()
    assert client.get("/merchant/me", headers=auth(user)).json()["pickup_address"] is None


def _sale(db, with_address):
    seller = make_user(db, "seller")
    m = MerchantAccount(user_id=seller.id, business_name="Shop", category="Fashion")
    if with_address:
        m.set_pickup_address({**ADDRESS, "country": "NG"})
    db.add(m)
    db.commit()
    product = make_product(db, merchant_id=m.id)
    order = Order(buyer_id=make_user(db, "buyer").id, buyer_name="B", product_id=product.id, product_name="Widget", price=10, status=OrderStatus.pending)
    db.add(order)
    db.commit()
    return seller, order


def test_a_live_test_cannot_start_until_the_seller_has_a_pickup_address(db):
    seller, order = _sale(db, with_address=False)
    with pytest.raises(seals.SealError) as e:
        seals.start_test(db, order.id, seller, "video/webm")
    assert getattr(e.value, "code", None) == "no_pickup_address" or "pickup address" in str(e.value).lower()


def test_the_courier_gets_the_address_in_terminal_africas_shape(db):
    _, order = _sale(db, with_address=True)
    got = courier.pickup_address_for(order)
    assert got["first_name"] == "Ada" and got["last_name"] == "Obi"
    assert got["line1"] == "12 Allen Avenue" and got["city"] == "Ikeja" and got["state"] == "Lagos"
    assert got["country"] == "NG" and got["zip"] == "100271" and got["phone"] == "+234 803 123 4567"
    assert got["email"].endswith("@t.test")


def test_no_courier_address_when_the_seller_has_none(db):
    _, order = _sale(db, with_address=False)
    assert courier.pickup_address_for(order) is None


def test_a_single_name_is_used_for_first_and_last(db):
    seller, order = _sale(db, with_address=True)
    m = order.product.merchant
    m.pickup_contact_name = "Ada"
    db.commit()
    got = courier.pickup_address_for(order)
    assert got["first_name"] == "Ada" and got["last_name"] == "Ada"
