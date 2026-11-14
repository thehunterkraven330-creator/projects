"""Terminal Africa client: payloads, rate choice, money, and the booking sequence. The network is never touched: _request is replaced."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import terminal


def test_a_phone_goes_out_in_international_form():
    pytest.importorskip("phonenumbers")
    a = terminal.address_payload(first_name="A", last_name="B", email=None, phone="0803 123 4567", line1="1 Rd", line2=None,
                                 city="Ikeja", state="Lagos", country="ng", zip_code="100271")
    assert a["phone"] == "+2348031234567" and a["country"] == "NG" and "email" not in a


def test_a_single_name_is_used_for_both_halves():
    assert terminal.split_name("Ada") == ("Ada", "Ada")
    assert terminal.split_name("Ada Obi Jr") == ("Ada", "Obi Jr")
    assert terminal.split_name("") == ("Customer", "Customer")


def test_weight_goes_out_in_kilograms_and_a_missing_weight_uses_the_default():
    p = terminal.parcel_payload(name="Shoe", value=Decimal("20"), currency="USD", weight_grams=450)
    assert p["weight_unit"] == "kg" and p["items"][0]["weight"] == 0.45
    d = terminal.parcel_payload(name="Shoe", value=Decimal("20"), currency="USD", weight_grams=None)
    assert d["items"][0]["weight"] == terminal.DEFAULT_WEIGHT_GRAMS / 1000


def test_the_cheapest_rate_is_chosen():
    rates = [{"rate_id": "RT-1", "amount": 9000}, {"rate_id": "RT-2", "amount": "4500.50"}, {"rate_id": "RT-3", "amount": 7000}]
    assert terminal.cheapest(rates)["rate_id"] == "RT-2"


def test_a_rate_without_an_amount_is_an_error():
    with pytest.raises(terminal.TerminalError):
        terminal.cheapest([{"rate_id": "RT-1"}])


def test_conversion_needs_a_configured_rate(monkeypatch):
    monkeypatch.delenv("TERMINAL_FX_NGN_USD", raising=False)
    assert terminal.convert(Decimal("100"), "usd", "USD") == Decimal("100")
    with pytest.raises(terminal.TerminalError):
        terminal.convert(Decimal("1000"), "NGN", "USD")
    monkeypatch.setenv("TERMINAL_FX_NGN_USD", "0.001")
    assert terminal.convert(Decimal("1000"), "NGN", "USD") == Decimal("1.000")


def test_the_buffer_is_added_and_rounded_up(monkeypatch):
    monkeypatch.setenv("SHIPPING_QUOTE_BUFFER_PERCENT", "10")
    assert terminal.with_buffer(Decimal("10.00")) == Decimal("11.00")
    assert terminal.with_buffer(Decimal("3.333")) == Decimal("3.67")  # 3.6663 rounds up


def _fake(monkeypatch, calls, rates):
    def fake(method, path, json=None, params=None):
        calls.append((method, path, json, params))
        if path == "/shipments/quick":
            return {"shipment_id": "SH-1"}
        if path == "/rates/shipment":
            return rates
        return {}

    monkeypatch.setattr(terminal, "_request", fake)


def test_quote_creates_a_shipment_asks_for_rates_and_converts(monkeypatch):
    terminal._quote_cache.clear()
    calls = []
    _fake(monkeypatch, calls, [{"rate_id": "RT-1", "amount": 5000, "currency": "NGN"}, {"rate_id": "RT-2", "amount": 3000, "currency": "NGN"}])
    monkeypatch.setenv("TERMINAL_FX_NGN_USD", "0.001")
    monkeypatch.setenv("SHIPPING_QUOTE_BUFFER_PERCENT", "10")
    pick = {"first_name": "A", "last_name": "B", "phone": "+2348031234567", "country": "NG"}
    price = terminal.quote_unit_shipping(pick, pick, name="Shoe", value=Decimal("20"), weight_grams=450, currency="USD")
    assert price == Decimal("3.30")  # 3000 NGN -> 3.00 USD + 10%
    assert [c[1] for c in calls] == ["/shipments/quick", "/rates/shipment"]
    assert calls[1][3] == {"shipment_id": "SH-1"}
    again = terminal.quote_unit_shipping(pick, pick, name="Shoe", value=Decimal("20"), weight_grams=450, currency="USD")
    assert again == price and len(calls) == 2  # the second one came from the cache


def test_a_response_without_a_shipment_id_is_an_error(monkeypatch):
    monkeypatch.setattr(terminal, "_request", lambda *a, **k: {"nope": 1})
    with pytest.raises(terminal.TerminalError):
        terminal.quick_shipment({}, {}, {})


def test_no_key_means_no_call(monkeypatch):
    monkeypatch.delenv("TERMINAL_AFRICA_SECRET_KEY", raising=False)
    with pytest.raises(terminal.TerminalError):
        terminal.get_rates("SH-1")


def test_the_courier_books_the_cheapest_rate(monkeypatch):
    pytest.importorskip("phonenumbers")
    calls = []
    _fake(monkeypatch, calls, [{"rate_id": "RT-9", "amount": 9000}, {"rate_id": "RT-2", "amount": 2000}])
    merchant = SimpleNamespace(
        has_pickup_address=True, pickup_contact_name="Ada Obi", pickup_phone="+2348031234567", pickup_line1="12 Allen Avenue",
        pickup_line2=None, pickup_city="Ikeja", pickup_state="Lagos", pickup_country="NG", pickup_postal_code="100271",
        user=SimpleNamespace(email="ada@t.test"),
    )
    order = SimpleNamespace(
        product=SimpleNamespace(merchant=merchant, weight_grams=300), product_name="Shoe", price=20,
        buyer=SimpleNamespace(email="b@t.test"),
        shipping_address={"recipient_name": "Bola Ade", "phone": "+2348031234568", "line1": "5 Rd", "line2": None, "city": "Lekki",
                          "state": "Lagos", "postal_code": "106104", "country": "NG"},
    )
    ref = terminal.TerminalCourier().request_pickup(SimpleNamespace(), order)
    assert ref == "SH-1"
    assert [c[1] for c in calls] == ["/shipments/quick", "/rates/shipment", "/shipments/pickup"]
    assert calls[2][2] == {"shipment_id": "SH-1", "rate_id": "RT-2"}
    body = calls[0][2]
    assert body["pickup_address"]["zip"] == "100271" and body["delivery_address"]["last_name"] == "Ade"
    assert body["parcel"]["items"][0]["weight"] == 0.3


def test_the_courier_refuses_a_seller_with_no_pickup_address():
    order = SimpleNamespace(product=SimpleNamespace(merchant=SimpleNamespace(has_pickup_address=False)), shipping_address={"x": 1})
    with pytest.raises(terminal.TerminalError):
        terminal.TerminalCourier().request_pickup(SimpleNamespace(), order)


def _signed(body: bytes, key="sk_test_x"):
    import hashlib
    import hmac

    return hmac.new(key.encode(), body, hashlib.sha512).hexdigest()


def test_a_correct_signature_is_accepted(monkeypatch):
    monkeypatch.setenv("TERMINAL_AFRICA_SECRET_KEY", "sk_test_x")
    body = b'{"event":"shipment.in-transit","data":{"shipment":"SH-1"}}'
    assert terminal.verify_signature(body, _signed(body))
    assert terminal.verify_signature(body, _signed(body).upper())  # hex case does not matter


@pytest.mark.parametrize("sig", [None, "", "abc", "0" * 128])
def test_a_wrong_or_missing_signature_is_refused(monkeypatch, sig):
    monkeypatch.setenv("TERMINAL_AFRICA_SECRET_KEY", "sk_test_x")
    assert not terminal.verify_signature(b"{}", sig)


def test_a_changed_body_or_key_is_refused(monkeypatch):
    monkeypatch.setenv("TERMINAL_AFRICA_SECRET_KEY", "sk_test_x")
    body = b'{"a":1}'
    sig = _signed(body)
    assert not terminal.verify_signature(b'{"a":2}', sig)
    monkeypatch.setenv("TERMINAL_AFRICA_SECRET_KEY", "sk_test_other")
    assert not terminal.verify_signature(body, sig)


def test_with_no_key_nothing_verifies(monkeypatch):
    monkeypatch.delenv("TERMINAL_AFRICA_SECRET_KEY", raising=False)
    assert not terminal.verify_signature(b"{}", _signed(b"{}", key=""))
