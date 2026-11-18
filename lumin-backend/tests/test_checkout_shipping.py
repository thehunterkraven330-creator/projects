"""What the buyer pays for delivery: the flat fee by default, a live courier rate (converted, buffered, per unit, per seller) when
COURIER=terminal, and the flat fee again whenever a live price cannot be had. The courier is replaced; the network is never touched."""
from decimal import Decimal

import pytest

from app import terminal
from app.models import MerchantAccount
from app.shipping import DEFAULT_SHIPPING_FLAT_FEE, compute_checkout_shipping
from tests.conftest import auth, make_product, make_user

BUYER_ADDRESS = {
    "recipient_name": "Bola Ade", "phone": "+2348031234568", "line1": "5 Rd", "line2": None, "city": "Lekki", "state": "Lagos",
    "postal_code": "106104", "country": "NG",
}
SELLER_ADDRESS = {
    "contact_name": "Ada Obi", "phone": "+2348031234567", "line1": "12 Allen Avenue", "line2": None, "city": "Ikeja",
    "state": "Lagos", "postal_code": "100271", "country": "NG",
}


def _seller(db, name="seller", with_address=True):
    user = make_user(db, name)
    m = MerchantAccount(user_id=user.id, business_name=f"{name} shop", category="Fashion")
    if with_address:
        m.set_pickup_address(SELLER_ADDRESS)
    db.add(m)
    db.commit()
    return m


def test_without_the_terminal_courier_it_is_the_flat_fee(db, monkeypatch):
    monkeypatch.delenv("COURIER", raising=False)
    p = make_product(db, merchant_id=_seller(db).id)
    assert compute_checkout_shipping(db, BUYER_ADDRESS, [(p, 3)]) == DEFAULT_SHIPPING_FLAT_FEE


def test_live_rate_is_charged_per_unit(db, monkeypatch):
    monkeypatch.setenv("COURIER", "terminal")
    monkeypatch.setattr(terminal, "quote_unit_shipping", lambda *a, **k: Decimal("3.30"))
    p = make_product(db, merchant_id=_seller(db).id)
    assert compute_checkout_shipping(db, BUYER_ADDRESS, [(p, 3)]) == Decimal("9.90")


def test_each_seller_is_priced_on_their_own(db, monkeypatch):
    monkeypatch.setenv("COURIER", "terminal")
    monkeypatch.setattr(terminal, "quote_unit_shipping", lambda *a, **k: Decimal("2.00"))
    a, b = make_product(db, merchant_id=_seller(db, "a").id), make_product(db, merchant_id=_seller(db, "b").id)
    assert compute_checkout_shipping(db, BUYER_ADDRESS, [(a, 1), (b, 2)]) == Decimal("6.00")


def test_the_flat_fee_is_used_when_terminal_cannot_price_it(db, monkeypatch):
    monkeypatch.setenv("COURIER", "terminal")

    def down(*a, **k):
        raise terminal.TerminalError("down")

    monkeypatch.setattr(terminal, "quote_unit_shipping", down)
    p = make_product(db, merchant_id=_seller(db).id)
    assert compute_checkout_shipping(db, BUYER_ADDRESS, [(p, 2)]) == DEFAULT_SHIPPING_FLAT_FEE


def test_a_seller_with_no_pickup_address_falls_back_to_the_flat_fee(db, monkeypatch):
    monkeypatch.setenv("COURIER", "terminal")
    monkeypatch.setattr(terminal, "quote_unit_shipping", lambda *a, **k: Decimal("9.99"))
    p = make_product(db, merchant_id=_seller(db, with_address=False).id)
    assert compute_checkout_shipping(db, BUYER_ADDRESS, [(p, 1)]) == DEFAULT_SHIPPING_FLAT_FEE


def test_a_bad_buyer_phone_falls_back_to_the_flat_fee(db, monkeypatch):
    pytest.importorskip("phonenumbers")
    monkeypatch.setenv("COURIER", "terminal")
    monkeypatch.setattr(terminal, "quote_unit_shipping", lambda *a, **k: Decimal("9.99"))
    p = make_product(db, merchant_id=_seller(db).id)
    assert compute_checkout_shipping(db, {**BUYER_ADDRESS, "phone": "123"}, [(p, 1)]) == DEFAULT_SHIPPING_FLAT_FEE


def test_the_address_the_buyer_enters_must_be_deliverable(client, db):
    user = make_user(db, "buyer2")
    bad = {**BUYER_ADDRESS, "country": "Nigeria"}
    r = client.patch("/users/me", json={"shipping_address": bad}, headers=auth(user))
    assert r.status_code == 400
    r = client.patch("/users/me", json={"shipping_address": {**BUYER_ADDRESS, "postal_code": ""}}, headers=auth(user))
    assert r.status_code == 400
    r = client.patch("/users/me", json={"shipping_address": BUYER_ADDRESS}, headers=auth(user))
    assert r.status_code == 200, r.text
    assert r.json()["shipping_address"]["phone"] == "+2348031234568"
