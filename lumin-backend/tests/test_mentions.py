from app.routers.video_posts import _MENTION_RE


def names(text):
    return [m.group(1) for m in _MENTION_RE.finditer(text)]


def test_finds_plain_mentions():
    assert names("@amaka thanks! and @john_doe. see you") == ["amaka", "john_doe"]


def test_keeps_dots_inside_a_name_but_not_the_full_stop_after_it():
    assert names("cc @Ada.Lovelace, nice") == ["Ada.Lovelace"]
    assert names("thanks @sam.") == ["sam"]


def test_email_addresses_are_not_mentions():
    assert names("write to a@b.com please") == []


def test_mention_in_brackets():
    assert names("(@sam) hi") == ["sam"]


# ---- the endpoints (need the test database, like the rest of the suite) ----
from app.models import Notification  # noqa: E402
from tests.conftest import auth, make_post, make_user  # noqa: E402


def _mention_notes(db, user):
    return [n for n in db.query(Notification).filter(Notification.user_id == user.id).all() if "mentioned you" in n.body]


def test_a_mentioned_person_is_told_once(client, db):
    owner, writer, friend = make_user(db, "owner"), make_user(db, "writer"), make_user(db, "friend")
    post = make_post(db, owner)
    text = f"hey @{friend.username} and again @{friend.username}"
    assert client.post(f"/video-posts/{post.id}/comments", json={"text": text}, headers=auth(writer)).status_code in (200, 201)
    assert len(_mention_notes(db, friend)) == 1
    assert _mention_notes(db, writer) == []


def test_nobody_is_told_twice_and_you_are_never_told_about_yourself(client, db):
    owner, writer = make_user(db, "owner"), make_user(db, "writer")
    post = make_post(db, owner)
    # mentioning the video's owner: they already get "commented on your video", so no second notice
    client.post(f"/video-posts/{post.id}/comments", json={"text": f"great @{owner.username}"}, headers=auth(writer))
    assert _mention_notes(db, owner) == []
    client.post(f"/video-posts/{post.id}/comments", json={"text": f"me @{writer.username}"}, headers=auth(writer))
    assert _mention_notes(db, writer) == []


def test_a_blocked_person_is_not_told(client, db):
    owner, writer, friend = make_user(db, "owner"), make_user(db, "writer"), make_user(db, "friend")
    post = make_post(db, owner)
    assert client.post(f"/users/{writer.id}/block", headers=auth(friend)).status_code == 204
    client.post(f"/video-posts/{post.id}/comments", json={"text": f"hi @{friend.username}"}, headers=auth(writer))
    assert _mention_notes(db, friend) == []


def test_editing_in_a_new_name_tells_only_the_new_person(client, db):
    owner, writer, a, b = (make_user(db, n) for n in ("owner", "writer", "aa", "bb"))
    post = make_post(db, owner)
    made = client.post(f"/video-posts/{post.id}/comments", json={"text": f"hi @{a.username}"}, headers=auth(writer)).json()
    assert len(_mention_notes(db, a)) == 1
    r = client.patch(f"/video-posts/comments/{made['id']}", json={"text": f"hi @{a.username} and @{b.username}"}, headers=auth(writer))
    assert r.status_code == 200, r.text
    assert len(_mention_notes(db, a)) == 1  # not told again
    assert len(_mention_notes(db, b)) == 1


def test_a_reply_carries_the_username_of_who_it_answers(client, db):
    owner, writer, other = make_user(db, "owner"), make_user(db, "writer"), make_user(db, "other")
    post = make_post(db, owner)
    top = client.post(f"/video-posts/{post.id}/comments", json={"text": "first"}, headers=auth(writer)).json()
    reply = client.post(f"/video-posts/{post.id}/comments", json={"text": "r1", "parent_id": top["id"]}, headers=auth(other)).json()
    answer = client.post(f"/video-posts/{post.id}/comments", json={"text": "r2", "parent_id": reply["id"]}, headers=auth(writer)).json()
    assert answer["reply_to_username"] == other.username
    listed = client.get(f"/video-posts/{post.id}/comments").json()
    assert {c["id"]: c["reply_to_username"] for c in listed}[answer["id"]] == other.username


def test_mention_suggestions(client, db):
    me, ada, adam, bob = make_user(db, "me"), make_user(db, "ada"), make_user(db, "adam"), make_user(db, "bob")
    got = client.get(f"/search/mentions?q={ada.username[:3]}", headers=auth(me)).json()
    names = [p["username"] for p in got]
    assert ada.username in names and adam.username in names and bob.username not in names
    assert set(got[0]) == {"id", "username", "display_name", "avatar_url"}  # nothing more than the list needs
    client.post(f"/users/{ada.id}/block", headers=auth(me))
    assert ada.username not in [p["username"] for p in client.get(f"/search/mentions?q={ada.username[:3]}", headers=auth(me)).json()]
