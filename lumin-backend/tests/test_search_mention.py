"""Searching "@name" finds people by username prefix (exact first) and nothing else."""
from tests.conftest import make_user


def named(db, username, display="Someone"):
    u = make_user(db, "x")
    u.username = username
    u.display_name = display
    db.commit()
    return u


def test_at_search_matches_username_prefix_exact_first(client, db):
    named(db, "adabella")
    named(db, "ada")
    named(db, "bada")  # contains "ada" but does not start with it
    named(db, "zed", display="Ada Lovelace")  # display name matches, username does not
    r = client.get("/search", params={"q": "@ada"}).json()
    assert [p["username"] for p in r["people"]["items"]] == ["ada", "adabella"]
    assert not (r.get("products") or {}).get("items") and r["people"]["total"] == 2


def test_at_search_ignores_wildcards_and_bare_at(client, db):
    named(db, "ada")
    assert client.get("/search", params={"q": "@"}).json()["people"]["items"] == []
    assert client.get("/search", params={"q": "@%"}).json()["people"]["items"] == []
    assert client.get("/search", params={"q": "@_da"}).json()["people"]["items"] == []


def test_plain_search_still_matches_anywhere(client, db):
    named(db, "bada")
    assert [p["username"] for p in client.get("/search", params={"q": "ada"}).json()["people"]["items"]] == ["bada"]
