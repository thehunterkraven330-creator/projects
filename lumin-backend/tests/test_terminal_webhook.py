"""Terminal's webhook events, as the app acts on them. The shipment lookup and the pickup rule are replaced so no database is needed."""
import json
from types import SimpleNamespace

import pytest

from app import shipments
from app.models.seal import SHIP_AWAITING, SHIP_IN_TRANSIT


@pytest.fixture
def ship(monkeypatch):
    s = SimpleNamespace(id="ship-1", order_id=None, status=SHIP_AWAITING)
    monkeypatch.setattr(shipments, "find_terminal_shipment", lambda db, ref: s if ref == "SH-1" else None)
    moved = []
    monkeypatch.setattr(shipments, "mark_picked_up", lambda db, sid, actor, name=None: moved.append(sid))
    s.moved = moved
    return s


def _event(name, ref="SH-1"):
    return {"event": name, "event_id": "EV-1", "data": {"shipment": ref}}


def test_in_transit_marks_the_driver_pickup(ship):
    assert shipments.handle_terminal_event(None, _event("shipment.in-transit")) == "picked_up"
    assert ship.moved == ["ship-1"]


def test_a_repeated_in_transit_does_nothing(ship):
    ship.status = SHIP_IN_TRANSIT
    assert shipments.handle_terminal_event(None, _event("shipment.in-transit")) == "ignored"
    assert ship.moved == []


def test_delivered_never_delivers_the_order(ship):
    assert shipments.handle_terminal_event(None, _event("shipment.delivered")) == "noted"
    assert ship.moved == [] and ship.status == SHIP_AWAITING


def test_a_shipment_that_is_not_ours_is_ignored(ship):
    assert shipments.handle_terminal_event(None, _event("shipment.in-transit", ref="SH-OTHER")) == "ignored"
    assert ship.moved == []


@pytest.mark.parametrize("payload", [{}, {"event": "shipment.in-transit"}, {"event": 5, "data": {"shipment": "SH-1"}},
                                    {"event": "shipment.in-transit", "data": "x"}, {"event": "address.created", "data": {"shipment": "SH-1"}}])
def test_malformed_or_unrelated_events_are_ignored(ship, payload):
    assert shipments.handle_terminal_event(None, payload) == "ignored"
    assert ship.moved == []


def test_the_route_checks_the_signature_first(client, monkeypatch):
    import hashlib
    import hmac

    monkeypatch.setenv("TERMINAL_AFRICA_SECRET_KEY", "sk_test_x")
    body = json.dumps(_event("shipment.in-transit")).encode()
    assert client.post("/courier/terminal-webhook", content=body).status_code == 401
    assert client.post("/courier/terminal-webhook", content=body, headers={"X-Terminal-Signature": "0" * 128}).status_code == 401
    sig = hmac.new(b"sk_test_x", body, hashlib.sha512).hexdigest()
    r = client.post("/courier/terminal-webhook", content=body, headers={"X-Terminal-Signature": sig})
    assert r.status_code == 200 and r.json()["result"] == "ignored"  # verified, but no such shipment in the test database


def test_the_route_is_off_without_a_key(client, monkeypatch):
    monkeypatch.delenv("TERMINAL_AFRICA_SECRET_KEY", raising=False)
    assert client.post("/courier/terminal-webhook", content=b"{}").status_code == 503


# ---- cancelling an order cancels the pickup at Terminal ----
def _cancel_setup(monkeypatch, courier_name="terminal", ref="SH-1", status=SHIP_AWAITING):
    from app import seals, terminal

    s = SimpleNamespace(id="ship-1", order_id="o1", bag_id="b1", status=status, courier=courier_name, courier_ref=ref, resolution=None, resolved_at=None)
    monkeypatch.setattr(shipments, "get_for_order", lambda db, oid: s)
    monkeypatch.setattr(seals, "advance", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(terminal, "cancel", lambda r: sent.append(r))
    return s, sent, terminal


def test_cancelling_a_waiting_order_cancels_the_terminal_pickup(monkeypatch):
    s, sent, _ = _cancel_setup(monkeypatch)
    shipments.on_order_cancelled(None, SimpleNamespace(id="o1"))
    assert sent == ["SH-1"] and s.status == "closed" and s.resolution == "cancelled"


def test_a_manual_courier_shipment_is_not_sent_to_terminal(monkeypatch):
    s, sent, _ = _cancel_setup(monkeypatch, courier_name="manual", ref=None)
    shipments.on_order_cancelled(None, SimpleNamespace(id="o1"))
    assert sent == [] and s.status == "closed"


def test_a_terminal_failure_does_not_block_the_cancellation(monkeypatch, caplog):
    s, sent, terminal = _cancel_setup(monkeypatch)

    def down(ref):
        raise terminal.TerminalError("down")

    monkeypatch.setattr(terminal, "cancel", down)
    shipments.on_order_cancelled(None, SimpleNamespace(id="o1"))
    assert s.status == "closed"
    assert "NOT cancelled at Terminal" in caplog.text


def test_an_order_with_the_driver_still_cannot_be_cancelled(monkeypatch):
    from app import seals

    s, sent, _ = _cancel_setup(monkeypatch, status=SHIP_IN_TRANSIT)
    with pytest.raises(seals.SealError):
        shipments.on_order_cancelled(None, SimpleNamespace(id="o1"))
    assert sent == []
