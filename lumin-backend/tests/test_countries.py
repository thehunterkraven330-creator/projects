"""The country map: which provider and currency each country uses, and that money only ever moves through the gateway that took it.
Pure code (no database): gateways are replaced, the network is never touched."""
import sys
from types import SimpleNamespace

import pytest

from app import countries, gateway, market, payment_provider


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("LAUNCH_COUNTRIES", raising=False)
    monkeypatch.delenv("ALLOW_UNVERIFIED_ROUTES", raising=False)
    monkeypatch.delenv("ALLOW_PAYSTACK_NON_NGN", raising=False)
    monkeypatch.setattr(payment_provider, "PROVIDER", "stripe")


def test_wave_one_is_the_default():
    assert countries.enabled_countries() == ["NG", "US", "GB"]
    assert countries.route_for("ng") == ("paystack", "NGN", False)
    assert countries.route_for("US").provider == "stripe" and countries.route_for("GB").currency == "GBP"
    assert countries.providers_in_use() == {"stripe", "paystack"}


def test_a_country_that_is_not_switched_on_has_no_route(monkeypatch):
    assert countries.route_for("DE") is None and countries.route_for(None) is None and countries.route_for("") is None
    monkeypatch.setenv("LAUNCH_COUNTRIES", "DE, US, zz")
    assert countries.enabled_countries() == ["DE", "US"]  # zz has no payment route, so it is ignored
    assert countries.route_for("DE") == ("stripe", "EUR", True)


def test_unverified_routes_are_flagged_until_allowed(monkeypatch):
    monkeypatch.setenv("LAUNCH_COUNTRIES", "NG,GH")
    assert countries.unverified_enabled() == ["GH"] and not countries.allow_unverified()
    monkeypatch.setenv("ALLOW_UNVERIFIED_ROUTES", "true")
    assert countries.allow_unverified()


def test_paystack_countries_pay_out_in_their_own_currency_only_for_naira_so_far():
    for cc in ("GH", "KE", "ZA"):
        assert countries.ROUTES[cc].provider == "paystack" and countries.ROUTES[cc].unverified
    assert not countries.ROUTES["NG"].unverified


def test_the_market_gate_follows_the_map(monkeypatch):
    assert market.is_open_in("US") and not market.is_open_in("DE") and not market.is_open_in(None)
    assert market.delivery_message() == "We only deliver to Nigeria, the United States and the United Kingdom right now."


def test_a_seller_is_paid_by_the_provider_of_their_country():
    assert payment_provider.merchant_provider(SimpleNamespace(pickup_country="NG")) == "paystack"
    assert payment_provider.merchant_provider(SimpleNamespace(pickup_country="us")) == "stripe"
    # no country said (an old account), or one we have no route for: this deployment's provider
    assert payment_provider.merchant_provider(SimpleNamespace(pickup_country=None)) == "stripe"
    assert payment_provider.merchant_provider(SimpleNamespace()) == "stripe"


def test_a_payment_remembers_its_provider_and_currency(monkeypatch):
    assert payment_provider.provider_of(SimpleNamespace(provider="paystack")) == "paystack"
    assert payment_provider.currency_of(SimpleNamespace(currency="ngn")) == "NGN"
    # a row from before provider was stored falls back to the deployment's
    assert payment_provider.provider_of(SimpleNamespace(provider=None)) == "stripe"
    assert payment_provider.currency_of(SimpleNamespace(currency=None)) == "USD"
    assert payment_provider.provider_of(None) == "stripe"


class _Fake:
    def __init__(self, name):
        self.name, self.calls = name, []

    def verify_transaction(self, ref):
        self.calls.append(("verify", ref))
        return {"status": "success", "amount": 1, "via": self.name}

    def refund_transaction(self, *a):
        self.calls.append(("refund",) + a)
        return {"via": self.name}


@pytest.fixture
def fakes(monkeypatch):
    stripe, paystack = _Fake("stripe"), _Fake("paystack")
    monkeypatch.setitem(sys.modules, "app.stripe_gateway", stripe)
    monkeypatch.setitem(sys.modules, "app.paystack", paystack)
    import app

    monkeypatch.setattr(app, "stripe_gateway", stripe, raising=False)
    monkeypatch.setattr(app, "paystack", paystack, raising=False)
    return stripe, paystack


def test_verify_and_refund_go_to_the_provider_named(fakes):
    stripe, paystack = fakes
    assert gateway.verify_transaction("r1", "paystack")["via"] == "paystack"
    assert gateway.verify_transaction("r2", "stripe")["via"] == "stripe"
    assert gateway.verify_transaction("r3")["via"] == "stripe"  # none named: the deployment's (stripe here)
    gateway.refund_transaction("p1", 500, "o1", provider="paystack")
    gateway.refund_transaction("s1", 500, "o2", provider="stripe")
    assert paystack.calls[-1] == ("refund", "p1", 500) and stripe.calls[-1] == ("refund", "s1", 500, "o2")


def test_money_is_never_paid_out_by_a_different_gateway_than_took_it():
    from fastapi import HTTPException

    order = SimpleNamespace(id="o", payment=SimpleNamespace(provider="paystack", reference="r"), payout_attempts=0)
    stripe_seller = SimpleNamespace(pickup_country="US", stripe_account_id="acct_1")
    with pytest.raises(HTTPException) as e:
        gateway.pay_seller(stripe_seller, order, 100, "x")
    assert e.value.status_code == 409
