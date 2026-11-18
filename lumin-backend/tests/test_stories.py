from datetime import timedelta

import pytest

from app import stories as stories_mod
from app.models import Story, UserBlock, follows
from tests.conftest import auth, make_product, make_user


@pytest.fixture(autouse=True)
def _files_exist(monkeypatch):
    # the picture was "uploaded": don't ask the real bucket
    monkeypatch.setattr("app.routers.stories.storage.key_from_view_url", lambda url: "k/" + url[-6:])
    monkeypatch.setattr("app.routers.stories.storage.object_exists", lambda key: True)
    monkeypatch.setattr("app.stories.storage.delete_object", lambda key: None)


def follow(db, a, b):
    db.execute(follows.insert().values(follower_id=a.id, followee_id=b.id))
    db.commit()


def post_story(client, user, **kw):
    body = {"media_url": "https://cdn.example/pic001.jpg", "media_type": "image", **kw}
    return client.post("/stories", json=body, headers=auth(user))


def test_my_story_shows_in_my_row_and_a_followers_row(client, db):
    me, fan = make_user(db, "me"), make_user(db, "fan")
    follow(db, fan, me)
    assert post_story(client, me, caption="hello").status_code == 201
    mine = client.get("/stories", headers=auth(me)).json()
    assert len(mine) == 1 and mine[0]["is_me"] is True and mine[0]["stories"][0]["caption"] == "hello"
    theirs = client.get("/stories", headers=auth(fan)).json()
    assert len(theirs) == 1 and theirs[0]["has_unseen"] is True and theirs[0]["stories"][0]["views_count"] is None


def test_someone_i_do_not_follow_is_not_in_my_row(client, db):
    me, other = make_user(db, "me"), make_user(db, "other")
    post_story(client, other)
    assert client.get("/stories", headers=auth(me)).json() == []


def test_followers_only_story_is_hidden_from_a_stranger_on_the_profile(client, db):
    author, fan, stranger = make_user(db, "author"), make_user(db, "fan"), make_user(db, "stranger")
    follow(db, fan, author)
    post_story(client, author, audience="followers")
    assert client.get(f"/stories/user/{author.id}", headers=auth(fan)).json() is not None
    assert client.get(f"/stories/user/{author.id}", headers=auth(stranger)).json() is None


def test_an_ended_story_is_gone(client, db):
    me = make_user(db, "me")
    sid = post_story(client, me).json()["id"]
    s = db.get(Story, sid)
    s.expires_at = stories_mod.now() - timedelta(minutes=1)
    db.commit()
    assert client.get("/stories", headers=auth(me)).json() == []


def test_purge_removes_stories_that_ended_over_an_hour_ago(client, db):
    me = make_user(db, "me")
    sid = post_story(client, me).json()["id"]
    db.get(Story, sid).expires_at = stories_mod.now() - timedelta(hours=2)
    db.commit()
    assert stories_mod.purge_expired(db) == 1
    assert db.get(Story, sid) is None


def test_seen_marking_and_the_viewers_list_are_for_the_author(client, db):
    author, fan = make_user(db, "author"), make_user(db, "fan")
    follow(db, fan, author)
    sid = post_story(client, author).json()["id"]
    assert client.post(f"/stories/{sid}/view", headers=auth(fan)).status_code == 204
    assert client.post(f"/stories/{sid}/view", headers=auth(fan)).status_code == 204  # twice is fine
    assert client.get("/stories", headers=auth(fan)).json()[0]["has_unseen"] is False
    assert [v["user"]["id"] for v in client.get(f"/stories/{sid}/viewers", headers=auth(author)).json()] == [str(fan.id)]
    assert client.get(f"/stories/{sid}/viewers", headers=auth(fan)).status_code == 404
    assert client.get("/stories", headers=auth(author)).json()[0]["stories"][0]["views_count"] == 1


def test_blocked_people_do_not_see_each_others_stories(client, db):
    author, fan = make_user(db, "author"), make_user(db, "fan")
    follow(db, fan, author)
    post_story(client, author)
    db.add(UserBlock(blocker_id=author.id, blocked_id=fan.id))
    db.commit()
    assert client.get("/stories", headers=auth(fan)).json() == []


def test_only_the_author_can_delete(client, db):
    author, other = make_user(db, "author"), make_user(db, "other")
    sid = post_story(client, author).json()["id"]
    assert client.delete(f"/stories/{sid}", headers=auth(other)).status_code == 404
    assert client.delete(f"/stories/{sid}", headers=auth(author)).status_code == 204
    assert client.get("/stories", headers=auth(author)).json() == []


def test_a_tagged_product_comes_back_with_the_story_and_is_not_marked_bought(client, db):
    me = make_user(db, "me")
    p = make_product(db)
    r = post_story(client, me, product_id=str(p.id)).json()
    assert r["product"]["id"] == str(p.id) and r["bought"] is False


def test_bad_media_type_is_refused(client, db):
    assert post_story(client, make_user(db, "me"), media_type="gif").status_code == 400


def test_enough_reports_hide_a_story_from_others(client, db):
    author, fan = make_user(db, "author"), make_user(db, "fan")
    follow(db, fan, author)
    sid = post_story(client, author).json()["id"]
    for i in range(3):
        rep = make_user(db, f"rep{i}")
        assert client.post("/reports", json={"target_type": "story", "target_id": sid, "reason": "spam"}, headers=auth(rep)).status_code == 201
    assert client.get("/stories", headers=auth(fan)).json() == []
    assert client.get("/stories", headers=auth(author)).json()[0]["stories"][0]["held"] is True


def test_reacting_shows_in_viewers_and_counts(client, db):
    author, fan = make_user(db, "author"), make_user(db, "fan")
    follow(db, fan, author)
    sid = post_story(client, author).json()["id"]
    assert client.post(f"/stories/{sid}/react", json={"emoji": "🔥"}, headers=auth(fan)).status_code == 204
    assert client.get("/stories", headers=auth(fan)).json()[0]["stories"][0]["my_reaction"] == "🔥"
    mine = client.get("/stories", headers=auth(author)).json()[0]["stories"][0]
    assert mine["reactions_count"] == 1 and mine["views_count"] == 1
    assert client.get(f"/stories/{sid}/viewers", headers=auth(author)).json()[0]["reaction"] == "🔥"
    assert client.post(f"/stories/{sid}/react", json={"emoji": "not-allowed"}, headers=auth(fan)).status_code == 400
    assert client.post(f"/stories/{sid}/react", json={"emoji": "🔥"}, headers=auth(author)).status_code == 400
    assert client.post(f"/stories/{sid}/react", json={"emoji": None}, headers=auth(fan)).status_code == 204
    assert client.get("/stories", headers=auth(author)).json()[0]["stories"][0]["reactions_count"] == 0


def test_rings_say_who_has_a_story_and_whether_it_is_new(client, db):
    author, fan, nobody = make_user(db, "author"), make_user(db, "fan"), make_user(db, "nobody")
    sid = post_story(client, author).json()["id"]  # fan does NOT follow: still visible, it is for everyone
    ids = f"{author.id},{nobody.id}"
    rings = client.get(f"/stories/rings?ids={ids}", headers=auth(fan)).json()
    assert rings == [{"user_id": str(author.id), "has_unseen": True}]
    client.post(f"/stories/{sid}/view", headers=auth(fan))
    assert client.get(f"/stories/rings?ids={ids}", headers=auth(fan)).json()[0]["has_unseen"] is False


def make_seller(db, name="seller"):
    """A person with a shop. Products belong to the shop (merchant_id is the MerchantAccount's id), not to the person."""
    from app.models import MerchantAccount

    user = make_user(db, name)
    shop = MerchantAccount(user_id=user.id, business_name="Shop", category="Fashion")
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return user, shop


def _soon(hours=2):
    from datetime import datetime, timezone

    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def test_seller_can_announce_a_live(client, db):
    seller, shop = make_seller(db)
    make_product(db, merchant_id=shop.id)
    r = post_story(client, seller, kind="live", event_at=_soon())
    assert r.status_code == 201 and r.json()["kind"] == "live" and r.json()["event_at"]


def test_non_seller_cannot_announce_a_live(client, db):
    assert post_story(client, make_user(db, "fan"), kind="live", event_at=_soon()).status_code == 400


def test_announcement_needs_a_future_time_within_a_day(client, db):
    seller, shop = make_seller(db)
    make_product(db, merchant_id=shop.id)
    assert post_story(client, seller, kind="live").status_code == 400
    assert post_story(client, seller, kind="live", event_at=_soon(-1)).status_code == 400
    assert post_story(client, seller, kind="live", event_at=_soon(30)).status_code == 400


def _sale(client, user, product, pct=30, hours=2, **kw):
    return post_story(client, user, kind="sale", event_at=_soon(hours), product_id=str(product.id), sale_percent=pct, **kw)


def test_flash_sale_rules(client, db):
    (seller, shop), other = make_seller(db), make_user(db, "other")
    p = make_product(db, price="100.00", merchant_id=shop.id)
    assert _sale(client, other, p).status_code == 400  # not their product
    assert post_story(client, seller, kind="sale", event_at=_soon(), product_id=str(p.id)).status_code == 400  # no percent
    assert _sale(client, seller, p, pct=2).status_code == 400  # too small
    assert _sale(client, seller, p, audience="followers").status_code == 400  # announcements are public
    p.discount_percent = 40
    db.commit()
    assert _sale(client, seller, p, pct=30).status_code == 400  # not bigger than the current discount


def test_flash_sale_runs_then_puts_the_old_discount_back(client, db):
    from datetime import datetime, timezone
    from decimal import Decimal

    seller, shop = make_seller(db)
    p = make_product(db, price="100.00", merchant_id=shop.id)
    p.discount_percent = 10
    db.commit()
    assert _sale(client, seller, p, pct=30).status_code == 201
    db.refresh(p)
    assert p.discount_percent == 30 and p.sale_price == Decimal("70.00")
    assert _sale(client, seller, p, pct=50, hours=3).status_code == 409  # one at a time
    # the time passes: the charge is the old price at once, and the worker puts the 10% back
    p.discount_ends_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    assert p.sale_price == Decimal("90.00")
    assert stories_mod.end_discounts(db) == 1
    db.refresh(p)
    assert p.discount_percent == 10 and p.discount_ends_at is None


def test_deleting_a_sale_story_ends_the_sale(client, db):
    seller, shop = make_seller(db)
    p = make_product(db, price="100.00", merchant_id=shop.id)
    r = _sale(client, seller, p)
    assert r.status_code == 201
    assert client.delete(f"/stories/{r.json()['id']}", headers=auth(seller)).status_code == 204
    db.refresh(p)
    assert p.discount_percent is None and p.discount_ends_at is None


def test_seller_editing_the_discount_by_hand_keeps_it(client, db):
    seller, shop = make_seller(db)
    p = make_product(db, merchant_id=shop.id)
    _sale(client, seller, p)
    p.discount_ends_at = None
    p.discount_restore_percent = None
    db.commit()
    assert stories_mod.end_discounts(db) == 0


def test_only_one_pending_live_per_seller(client, db):
    seller, shop = make_seller(db)
    make_product(db, merchant_id=shop.id)
    assert post_story(client, seller, kind="live", event_at=_soon()).status_code == 201
    assert post_story(client, seller, kind="live", event_at=_soon(3)).status_code == 409


def test_followers_are_told_about_a_live_but_not_an_ordinary_story(client, db):
    from app.models import Notification

    seller, shop = make_seller(db)
    make_product(db, merchant_id=shop.id)
    fan = make_user(db, "fan")
    follow(db, fan, seller)
    post_story(client, seller, caption="just a pic")
    assert db.query(Notification).filter(Notification.user_id == fan.id).count() == 0
    assert post_story(client, seller, kind="live", event_at=_soon()).status_code == 201
    told = db.query(Notification).filter(Notification.user_id == fan.id).all()
    assert len(told) == 1 and told[0].type.value == "story" and "going live" in told[0].body


def test_explore_lists_public_seller_updates_from_people_i_do_not_follow(client, db):
    seller, shop = make_seller(db, "shopper")
    followed, fshop = make_seller(db, "followed")
    plain = make_user(db, "plain")
    viewer = make_user(db, "viewer")
    follow(db, viewer, followed)
    post_story(client, seller, caption="public from a seller")
    post_story(client, seller, caption="followers only", audience="followers")
    post_story(client, followed, caption="someone I follow")
    post_story(client, plain, caption="a person, not a shop")
    got = client.get("/stories/explore", headers=auth(viewer)).json()
    assert [g["author"]["id"] for g in got] == [str(seller.id)]
    assert [s["caption"] for s in got[0]["stories"]] == ["public from a seller"]


def test_explore_hides_a_blocked_seller(client, db):
    seller, shop = make_seller(db, "shopper")
    viewer = make_user(db, "viewer")
    post_story(client, seller)
    db.add(UserBlock(blocker_id=viewer.id, blocked_id=seller.id))
    db.commit()
    assert client.get("/stories/explore", headers=auth(viewer)).json() == []


def test_updates_list_puts_the_people_you_engage_with_first(client, db):
    from app.models import StoryView
    from app.models import Story as StoryRow

    viewer = make_user(db, "viewer")
    quiet, close = make_user(db, "quiet"), make_user(db, "close")
    follow(db, viewer, quiet)
    follow(db, viewer, close)
    post_story(client, close, caption="close old")  # posted first, so older
    post_story(client, close, caption="close new")  # a second one, so reacting to the first leaves them with something unseen
    post_story(client, quiet, caption="quiet one")  # newest of all
    # with no interaction at all the newest comes first
    first = [g["author"]["id"] for g in client.get("/stories", headers=auth(viewer)).json()]
    assert first == [str(quiet.id), str(close.id)]
    # the viewer reacts to one of close's old updates (a signal), and close moves to the top
    old = db.query(StoryRow).filter(StoryRow.author_id == close.id, StoryRow.caption == "close old").first()
    db.add(StoryView(story_id=old.id, viewer_id=viewer.id, reaction="fire"))
    db.commit()
    second = [g["author"]["id"] for g in client.get("/stories", headers=auth(viewer)).json()]
    assert second[0] == str(close.id)
