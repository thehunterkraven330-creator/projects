from app import seed
from app.auth.security import hash_password
from app.models import Category, User
from tests.conftest import make_user


def make_demo(db, email, password=seed.DEMO_PASSWORD):
    user = make_user(db, "demo")
    user.email = email
    user.hashed_password = hash_password(password)
    db.commit()
    return user


def test_finds_only_accounts_with_the_public_password(db):
    make_demo(db, "admin@example.com")
    make_demo(db, "someone@example.com", "a-real-password")  # example.com but not the demo password
    make_demo(db, "real@gmail.com")  # demo password but not the demo domain
    assert [u.email for u in seed.demo_accounts(db)] == ["admin@example.com"]


def test_check_flags_powerful_demo_accounts(db, capsys):
    make_demo(db, "admin@example.com")
    assert seed.check() == 1
    assert "PUBLIC password" in capsys.readouterr().out


def test_check_is_quiet_when_clean(db, capsys):
    make_demo(db, "real@gmail.com", "a-real-password")
    assert seed.check() == 0
    assert capsys.readouterr().out == ""


def test_remove_demo_deletes_them_and_nobody_else(db):
    make_demo(db, "admin@example.com")
    make_demo(db, "you@example.com")
    keep = make_demo(db, "real@gmail.com", "a-real-password")
    assert seed.remove_demo() == 2
    db.expire_all()
    assert [u.email for u in db.query(User).all()] == [keep.email]


def test_basics_creates_categories_once_and_no_people(db):
    seed.run_basics()
    seed.run_basics()
    names = [c.name for c in db.query(Category).all()]
    assert len(names) == 4 and len(set(names)) == 4
    assert db.query(User).count() == 0


def test_basics_gives_every_category_a_collection_so_a_seller_can_list_a_product(db):
    from app.models import CategoryBanner

    seed.run_basics()
    seed.run_basics()  # once only
    cats = db.query(Category).all()
    assert db.query(CategoryBanner).count() == len(cats) == 4
    assert all(len(c.banners) == 1 and c.banners[0].title == f"All {c.name}" for c in cats)


def test_basics_repairs_a_database_that_has_categories_but_no_collections_and_leaves_admin_ones_alone(db):
    from app.models import CategoryBanner

    seed.run_basics()
    apparel = db.query(Category).filter_by(name="Apparel").one()
    db.query(CategoryBanner).filter(CategoryBanner.category_id != apparel.id).delete()
    db.query(CategoryBanner).filter_by(category_id=apparel.id).update({"title": "Summer sale"})
    db.commit()
    seed.run_basics()
    db.expire_all()
    assert [b.title for b in apparel.banners] == ["Summer sale"]  # the admin's own collection is not added to
    assert all(len(c.banners) >= 1 for c in db.query(Category).all())
