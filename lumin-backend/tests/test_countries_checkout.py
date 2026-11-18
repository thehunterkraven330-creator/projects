"""Checkout picks the gateway and currency from the country the order is delivered to, and refuses an order that is not domestic.
Needs the test database (like the other checkout tests)."""
from app import countries
from app.models import MerchantAccount, Payment
from tests.conftest import auth, make_product, make_user

# The buyer fixture's saved address is in Nigeria (tests/conftest.py ADDRESS).


def _seller(db, country):
    u = make_user(db, f"seller_{country.lower()}")
    m = MerchantAccount(user_id=u.id, business_name="Shop", category="Fashion", pickup_country=country)
    db.add(m)
    db.commit()
    return m


def _init(client, buyer, product):
    return client.post("/payments/initialize", headers=auth(buyer), json={"mode": "buy_now", "product_id": str(product.id), "quantity": 1})


def test_a_nigerian_order_is_charged_by_paystack_in_naira(client, db, buyer):
    p = make_product(db, merchant_id=_seller(db, "NG").id)
    r = _init(client, buyer, p)
    assert r.status_code == 201, r.text
    assert r.json()["provider"] == "paystack" and r.json()["currency"] == "NGN"
    pay = db.query(Payment).filter_by(reference=r.json()["reference"]).one()
    assert pay.provider == "paystack" and pay.currency == "NGN"


def test_a_seller_in_another_country_cannot_sell_to_this_buyer(client, db, buyer):
    p = make_product(db, merchant_id=_seller(db, "US").id)
    r = _init(client, buyer, p)
    assert r.status_code == 409 and "another country" in r.json()["detail"]
    assert db.query(Payment).count() == 0


def test_a_country_not_switched_on_is_refused(client, db, buyer, monkeypatch):
    monkeypatch.setenv("LAUNCH_COUNTRIES", "US,GB")  # the buyer's address is in Nigeria
    p = make_product(db, merchant_id=_seller(db, "US").id)
    r = _init(client, buyer, p)
    assert r.status_code == 409 and "only deliver to" in r.json()["detail"]


def test_a_seller_with_no_country_is_accepted_only_where_the_deployments_provider_applies(client, db, buyer, monkeypatch):
    u = make_user(db, "oldseller")
    m = MerchantAccount(user_id=u.id, business_name="Old", category="Fashion")
    db.add(m)
    db.commit()
    p = make_product(db, merchant_id=m.id)
    assert _init(client, buyer, p).status_code == 201  # deployment provider paystack, buyer in Nigeria (paystack)
    monkeypatch.setitem(countries.ROUTES, "NG", countries.Route("stripe", "USD"))
    assert _init(client, buyer, p).status_code == 409  # now the country's provider differs from the old seller's default


def test_the_product_says_which_currency_its_price_is_in(client, db, buyer):
    p = make_product(db, merchant_id=_seller(db, "NG").id)
    body = client.get(f"/products/{p.id}", headers=auth(buyer)).json()
    assert body["currency"] == "NGN"
