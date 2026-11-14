"""The Paystack path for a naira launch: the one charge currency, the market gate, safe payouts (no double payment, no pretending
an unconfirmed transfer was sent), and what happens when a payout bounces. Paystack itself is replaced; the network is never touched."""
from types import SimpleNamespace

import pytest

from app import market, paystack, payment_provider


# ---- the charge currency ----
@pytest.mark.parametrize(
    "provider,env,expected",
    [("paystack", {}, "NGN"), ("stripe", {}, "USD"), ("paystack", {"PAYMENT_CURRENCY": "ghs"}, "GHS"),
     ("paystack", {"PAYSTACK_CURRENCY": "USD"}, "USD"), ("stripe", {"PAYMENT_CURRENCY": "gbp"}, "GBP")],
)
def test_charge_currency(monkeypatch, provider, env, expected):
    monkeypatch.setattr(payment_provider, "PROVIDER", provider)
    monkeypatch.delenv("PAYMENT_CURRENCY", raising=False)
    monkeypatch.delenv("PAYSTACK_CURRENCY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert payment_provider.charge_currency() == expected


# ---- the market gate ----
def test_no_launch_countries_means_wave_one(monkeypatch):
    monkeypatch.delenv("LAUNCH_COUNTRIES", raising=False)
    assert market.launch_countries() == ["NG", "US", "GB"]
    assert market.is_open_in("US") and not market.is_open_in("FR") and not market.is_open_in(None)


def test_launch_countries_limit_where_we_are_open(monkeypatch):
    monkeypatch.setenv("LAUNCH_COUNTRIES", "ng, gh, xx")
    assert market.launch_countries() == ["NG", "GH"]  # a code with no payment route is ignored
    assert market.is_open_in("ng") and market.is_open_in("GH") and not market.is_open_in("US") and not market.is_open_in("")
    assert market.delivery_message() == "We only deliver to Nigeria and Ghana right now."
    monkeypatch.setenv("LAUNCH_COUNTRIES", "NG")
    assert market.seller_message() == "We're only taking sellers in Nigeria right now."


def test_an_order_must_be_domestic():
    assert not market.domestic_conflict("NG", ["NG", "ng"])
    assert market.domestic_conflict("NG", ["NG", "GH"])
    assert not market.domestic_conflict("NG", [None, ""])  # a seller who never said where they collect from is not checked


# ---- payouts ----
def test_a_payout_reference_is_stable_per_attempt_and_fits_paystacks_rules():
    oid = "123e4567-e89b-12d3-a456-426614174000"
    first = paystack.transfer_reference(oid)
    assert first == paystack.transfer_reference(oid) and first != paystack.transfer_reference(oid, 1)
    for ref in (first, paystack.transfer_reference(oid, 5)):
        assert 16 <= len(ref) <= 50 and ref == ref.lower() and all(c.isalnum() or c in "-_" for c in ref)


class _Resp:
    def __init__(self, code, data=None):
        self.status_code, self._data = code, data

    def json(self):
        return {"data": self._data}


def _http(monkeypatch, post=None, get=None):
    monkeypatch.setattr(paystack, "httpx", SimpleNamespace(post=post or (lambda *a, **k: _Resp(500)), get=get or (lambda *a, **k: _Resp(404)), HTTPError=Exception))
    sent = []
    return sent


def test_a_transfer_sends_naira_and_our_reference(monkeypatch):
    seen = {}
    _http(monkeypatch, post=lambda url, **k: seen.update(k["json"]) or _Resp(200, {"status": "pending", "transfer_code": "TRF_1"}))
    out = paystack.create_transfer("RCP_1", 150000, "Payout", reference="lumin-po-abc-123456789")
    assert out["transfer_code"] == "TRF_1"
    assert seen["currency"] == "NGN" and seen["amount"] == 150000 and seen["reference"] == "lumin-po-abc-123456789"


def test_a_transfer_waiting_for_an_otp_is_not_treated_as_sent(monkeypatch):
    _http(monkeypatch, post=lambda *a, **k: _Resp(200, {"status": "otp", "transfer_code": "TRF_1"}))
    with pytest.raises(Exception) as e:
        paystack.create_transfer("RCP_1", 1, "x", reference="r" * 20)
    assert e.value.status_code == 502 and "confirmation" in e.value.detail


def test_a_failed_transfer_is_an_error(monkeypatch):
    _http(monkeypatch, post=lambda *a, **k: _Resp(200, {"status": "failed", "transfer_code": "TRF_1"}))
    with pytest.raises(Exception) as e:
        paystack.create_transfer("RCP_1", 1, "x", reference="r" * 20)
    assert e.value.status_code == 502


def test_a_repeated_payout_returns_the_one_already_sent(monkeypatch):
    # Paystack refuses the second call (same reference), we ask what happened to the first, and do not send again.
    _http(monkeypatch, post=lambda *a, **k: _Resp(400), get=lambda *a, **k: _Resp(200, {"status": "success", "transfer_code": "TRF_1"}))
    assert paystack.create_transfer("RCP_1", 1, "x", reference="r" * 20)["transfer_code"] == "TRF_1"


def test_a_rejected_transfer_with_no_earlier_one_is_an_error(monkeypatch):
    _http(monkeypatch, post=lambda *a, **k: _Resp(400), get=lambda *a, **k: _Resp(404))
    with pytest.raises(Exception) as e:
        paystack.create_transfer("RCP_1", 1, "x", reference="r" * 20)
    assert e.value.status_code == 502


def test_the_gateway_gives_each_attempt_its_own_reference(monkeypatch):
    from app import gateway

    monkeypatch.setattr(payment_provider, "PROVIDER", "paystack")
    got = []
    monkeypatch.setattr(paystack, "create_transfer", lambda **kw: got.append(kw) or {"transfer_code": "TRF_1"})
    merchant = SimpleNamespace(paystack_recipient_code="RCP_1")
    order = SimpleNamespace(id="123e4567-e89b-12d3-a456-426614174000", payout_attempts=0)
    assert gateway.pay_seller(merchant, order, 5000, "x") == "TRF_1"
    order.payout_attempts = 2
    gateway.pay_seller(merchant, order, 5000, "x")
    assert got[0]["reference"] != got[1]["reference"] and got[1]["reference"].endswith("-2")
    assert got[0]["recipient_code"] == "RCP_1" and got[0]["amount_subunit"] == 5000
