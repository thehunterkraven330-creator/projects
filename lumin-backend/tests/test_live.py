"""Live shopping: only business accounts go live; anyone signed in joins, chats, and is counted; stale or ended streams drop off."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.models import LiveStream, MerchantAccount
from tests.conftest import auth, make_product, make_user


@pytest.fixture(autouse=True)
def _livekit(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.test")
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "devsecret-devsecret-devsecret-12345")
    monkeypatch.setattr("app.live.close_room", lambda room: None)


def merchant(db, name="host"):
    user = make_user(db, name)
    m = MerchantAccount(user_id=user.id, business_name="Shop", category="Fashion", description="")
    db.add(m)
    db.commit()
    db.refresh(m)
    return user, m


def test_only_a_business_account_can_go_live(client, db):
    buyer = make_user(db, "buyer")
    assert client.post("/live", json={"title": "Hi"}, headers=auth(buyer)).status_code == 403


def test_go_live_returns_a_publish_token_and_lists_it(client, db):
    host, m = merchant(db)
    product = make_product(db, merchant_id=m.id)
    r = client.post("/live", json={"title": "New drop", "product_ids": [str(product.id)]}, headers=auth(host))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_host"] is True and body["url"] == "wss://lk.test"
    claims = jwt.decode(body["token"], "devsecret-devsecret-devsecret-12345", algorithms=["HS256"], options={"verify_aud": False})
    assert claims["iss"] == "devkey" and claims["video"]["canPublish"] is True and claims["video"]["room"].startswith("live-")
    listed = client.get("/live").json()
    assert [s["title"] for s in listed] == ["New drop"] and listed[0]["products"][0]["id"] == str(product.id)


def test_cannot_show_someone_elses_product(client, db):
    host, _ = merchant(db)
    other, om = merchant(db, "other")
    theirs = make_product(db, merchant_id=om.id)
    r = client.post("/live", json={"title": "x", "product_ids": [str(theirs.id)]}, headers=auth(host))
    assert r.status_code == 422


def test_viewer_gets_a_watch_only_token_and_is_counted(client, db):
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    j = client.post(f"/live/{sid}/join", headers=auth(viewer)).json()
    claims = jwt.decode(j["token"], "devsecret-devsecret-devsecret-12345", algorithms=["HS256"], options={"verify_aud": False})
    assert j["is_host"] is False and claims["video"]["canPublish"] is False and claims["video"]["canSubscribe"] is True
    page = client.get(f"/live/{sid}/messages", headers=auth(viewer)).json()
    assert page["status"] == "live" and page["viewer_count"] == 1


def test_chat_flows_in_order_and_after_filter_works(client, db):
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    first = client.post(f"/live/{sid}/messages", json={"body": "  hello  "}, headers=auth(viewer)).json()
    client.post(f"/live/{sid}/messages", json={"body": "price?"}, headers=auth(viewer))
    client.post(f"/live/{sid}/messages", json={"body": "it is 10"}, headers=auth(host))
    page = client.get(f"/live/{sid}/messages?after={first['id']}", headers=auth(viewer)).json()
    assert [m["body"] for m in page["messages"]] == ["price?", "it is 10"]
    assert [m["is_host"] for m in page["messages"]] == [False, True]
    assert first["body"] == "hello"


def test_ending_stops_chat_and_listing(client, db):
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    assert client.post(f"/live/{sid}/end", headers=auth(viewer)).status_code == 403  # not the host
    assert client.post(f"/live/{sid}/end", headers=auth(host)).status_code == 204
    assert client.get("/live").json() == []
    assert client.post(f"/live/{sid}/messages", json={"body": "late"}, headers=auth(viewer)).status_code == 409
    assert client.post(f"/live/{sid}/join", headers=auth(viewer)).status_code == 409
    assert client.get(f"/live/{sid}/messages", headers=auth(viewer)).json()["status"] == "ended"


def test_a_quiet_host_is_treated_as_gone(client, db):
    host, _ = merchant(db)
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    s = db.get(LiveStream, uuid.UUID(sid))
    s.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    assert client.get("/live").json() == []


def test_going_live_again_ends_the_old_one(client, db):
    host, _ = merchant(db)
    client.post("/live", json={"title": "One"}, headers=auth(host))
    client.post("/live", json={"title": "Two"}, headers=auth(host))
    assert [s["title"] for s in client.get("/live").json()] == ["Two"]


def test_blocked_people_cannot_join_or_see_it(client, db):
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    client.post(f"/users/{host.id}/block", headers=auth(viewer))
    assert client.post(f"/live/{sid}/join", headers=auth(viewer)).status_code == 403
    assert client.get("/live", headers=auth(viewer)).json() == []


def test_not_configured_says_so(client, db, monkeypatch):
    monkeypatch.delenv("LIVEKIT_URL")
    host, _ = merchant(db)
    assert client.post("/live", json={"title": "Hi"}, headers=auth(host)).status_code == 503


def test_followers_are_told_once_when_a_merchant_goes_live(client, db):
    from app.models import Notification, NotificationType, follows

    host, _ = merchant(db)
    fan = make_user(db, "fan")
    stranger = make_user(db, "stranger")
    db.execute(follows.insert().values(follower_id=fan.id, followee_id=host.id))
    db.commit()
    sid = client.post("/live", json={"title": "Sneaker drop"}, headers=auth(host)).json()["stream"]["id"]
    client.post("/live", json={"title": "Again"}, headers=auth(host))  # restarting must not notify twice
    notes = db.query(Notification).filter(Notification.type == NotificationType.live).all()
    assert [n.user_id for n in notes] == [fan.id]
    assert notes[0].actor_id == host.id and "Sneaker drop" in notes[0].body and str(notes[0].target_id) == sid
    assert stranger.id not in [n.user_id for n in notes]


def test_hearts_add_up_and_show_in_the_poll(client, db):
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    assert client.post(f"/live/{sid}/hearts", json={"count": 3}, headers=auth(viewer)).status_code == 204
    client.post(f"/live/{sid}/hearts", json={"count": 2}, headers=auth(viewer))
    assert client.get(f"/live/{sid}/messages", headers=auth(viewer)).json()["hearts"] == 5
    assert client.post(f"/live/{sid}/hearts", json={"count": 99}, headers=auth(viewer)).status_code == 422


def test_recorded_live_gets_a_replay_after_it_ends(client, db, monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://cdn.test")
    monkeypatch.setattr("app.live.recording_enabled", lambda: True)
    monkeypatch.setattr("app.live.start_recording", lambda room, sid: "EG_1")
    monkeypatch.setattr("app.live.stop_recording", lambda egress: None)
    host, _ = merchant(db)
    viewer = make_user(db, "viewer")
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    assert client.post(f"/live/{sid}/recording", headers=auth(viewer)).status_code == 403
    assert client.post(f"/live/{sid}/recording", headers=auth(host)).status_code == 204
    assert client.get("/live/replays").json() == []  # still live
    client.post(f"/live/{sid}/end", headers=auth(host))
    replays = client.get("/live/replays").json()
    assert [r["id"] for r in replays] == [sid] and replays[0]["replay_url"] == f"https://cdn.test/live/{sid}.mp4"


def test_unrecorded_live_has_no_replay(client, db, monkeypatch):
    monkeypatch.setattr("app.live.start_recording", lambda room, sid: None)
    host, _ = merchant(db)
    sid = client.post("/live", json={"title": "Hi"}, headers=auth(host)).json()["stream"]["id"]
    client.post(f"/live/{sid}/recording", headers=auth(host))
    client.post(f"/live/{sid}/end", headers=auth(host))
    assert client.get("/live/replays").json() == []
