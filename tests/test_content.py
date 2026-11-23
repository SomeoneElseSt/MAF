"""Posts, comments, labels, views and the listing pages."""

from datetime import timedelta

import pytest

from maf import store
from maf.util import iso, utc_now



@pytest.fixture
def client(starlette_app, app):
    """These pages are students-only, so the client here is signed in as a reader."""
    from starlette.testclient import TestClient

    from tests.conftest import sign_in_as

    return sign_in_as(TestClient(starlette_app), app, store.create_pass(app.conn))

def make_post(app, pass_id, title="A post", text="Some text", url=None, tags=(), days_ago=0):
    created = iso(utc_now() - timedelta(days=days_ago))
    return store.create_post(app.conn, pass_id, title, text, url, list(tags), created_at=created)


def make_comment(app, pass_id, parent, text="A comment", private_to=None):
    return store.create_comment(app.conn, pass_id, parent, text, private_to)


# -- item ids ------------------------------------------------------------


def test_things_list_is_clean():
    from maf.wordlist import ADJECTIVES, ANIMALS, THINGS

    assert len(THINGS) == 256 and len(set(THINGS)) == 256
    assert all(word.isalpha() and word.islower() for word in THINGS)
    assert not set(THINGS) & (set(ADJECTIVES) | set(ANIMALS))


def test_item_id_is_adjective_thing_thing():
    from maf.util import new_item_id
    from maf.wordlist import ADJECTIVES, THINGS

    for _ in range(200):
        adjective, first, second = new_item_id().split("-")
        assert adjective in ADJECTIVES and first in THINGS and second in THINGS
        assert first != second


def test_created_items_get_three_word_ids_and_never_reuse_one(app, pass_id, monkeypatch):
    taken = store.create_post(app.conn, pass_id, "First", None, None, []).id
    ids = iter([taken, taken, "quiet-river-lantern"])
    monkeypatch.setattr(store, "new_item_id", lambda: next(ids))
    second = store.create_post(app.conn, pass_id, "Second", None, None, [])
    assert second.id == "quiet-river-lantern"
    assert len(taken.split("-")) == 3


# -- labels --------------------------------------------------------------


def test_label_is_stable_within_a_thread_and_differs_across_threads(app):
    labeler = app.labeler
    assert labeler.label("pass-a", "thread-1") == labeler.label("pass-a", "thread-1")
    assert labeler.label("pass-a", "thread-1") != labeler.label("pass-a", "thread-2")
    assert labeler.label("pass-a", "thread-1") != labeler.label("pass-b", "thread-1")


def test_label_shape(app):
    label = app.labeler.label("pass-a", "thread-1")
    adjective, animal = label.split("-")
    from maf.wordlist import ADJECTIVES, ANIMALS

    assert adjective in ADJECTIVES and animal in ANIMALS


def test_label_depends_on_the_secret():
    from maf.labels import Labeler

    assert Labeler(b"one").label("p", "t") != Labeler(b"two").label("p", "t")


# -- posts and comments --------------------------------------------------


def test_post_is_stored_with_tags(app, pass_id):
    post = make_post(app, pass_id, tags=["berlin", "help"])
    assert post.title == "A post"
    assert post.tags == ["berlin", "help"]
    assert post.thread_id == post.id
    assert post.parent_id is None


def test_comment_nests_under_its_parent(app, pass_id):
    post = make_post(app, pass_id)
    first = make_comment(app, pass_id, post)
    second = make_comment(app, pass_id, first)
    assert second.thread_id == post.id
    assert second.parent_id == first.id
    items = store.thread_items(app.conn, post.id, pass_id)
    tree = store.build_tree(items, post.id)
    assert tree[0]["item"].id == first.id
    assert tree[0]["children"][0]["item"].id == second.id


def test_comment_count_excludes_private(app, pass_id):
    post = make_post(app, pass_id)
    make_comment(app, pass_id, post)
    make_comment(app, pass_id, post, private_to="someone")
    app.conn.execute("UPDATE item SET private_to = ? WHERE private_to = 'someone'", (pass_id,))
    app.conn.commit()
    assert store.comment_count(app.conn, post.id) == 1


# -- views ---------------------------------------------------------------


def test_view_counts_once_per_pass_per_day(client, signed_in, app, pass_id):
    post = make_post(app, pass_id)
    for _ in range(3):
        client.get(f"/item/{post.id}")
    assert store.get_item(app.conn, post.id).views == 1


def test_view_dedupe_clears_after_24_hours(app, pass_id):
    assert app.memory.count_view(pass_id, "item-1")
    assert not app.memory.count_view(pass_id, "item-1")
    # a fresh Memory (a restart) forgets the dedupe set
    from maf.memory import Memory

    assert Memory().count_view(pass_id, "item-1")


def test_signed_out_visitors_cannot_open_threads_or_add_views(starlette_app, app, pass_id):
    from starlette.testclient import TestClient

    post = make_post(app, pass_id, title="Students only")
    response = TestClient(starlette_app).get(f"/item/{post.id}", follow_redirects=False)
    assert response.status_code == 303
    assert "Students only" not in response.text
    assert store.get_item(app.conn, post.id).views == 0


# -- four-day pages ------------------------------------------------------


def test_home_shows_four_days_grouped_by_day(client, app, pass_id):
    make_post(app, pass_id, title="Today post", days_ago=0)
    make_post(app, pass_id, title="Older post", days_ago=3)
    make_post(app, pass_id, title="Too old", days_ago=4)
    body = client.get("/").text
    assert "Today post" in body and "Older post" in body
    assert "Too old" not in body
    assert "Today" in body


def test_before_steps_back_four_days(client, app, pass_id):
    make_post(app, pass_id, title="Six days ago", days_ago=6)
    before = (utc_now().date() - timedelta(days=3)).isoformat()
    body = client.get(f"/?before={before}").text
    assert "Six days ago" in body


def test_sort_old_starts_at_the_earliest_posts(client, app, pass_id):
    make_post(app, pass_id, title="Very first", days_ago=40)
    make_post(app, pass_id, title="Recent", days_ago=0)
    body = client.get("/?sort=old").text
    assert "Very first" in body
    assert "Recent" not in body


def test_sort_views_orders_by_views(client, app, pass_id):
    quiet = make_post(app, pass_id, title="Quiet post")
    loud = make_post(app, pass_id, title="Loud post")
    app.conn.execute("UPDATE item SET views = 50 WHERE id = ?", (loud.id,))
    app.conn.commit()
    body = client.get("/?sort=views").text
    assert body.index("Loud post") < body.index("Quiet post")


def test_pinned_posts_show_above_today_only_on_newest_latest(client, app, pass_id):
    pinned = make_post(app, pass_id, title="Welcome post")
    store.set_pinned(app.conn, pinned.id, True)
    make_post(app, pass_id, title="A normal post")
    body = client.get("/").text
    main = body.split("<main")[1].split("</main>")[0]
    assert main.index(">Pinned<") < main.index(">Today<")
    assert main.count('class="title" href="/item/') == main.count(">Welcome post<") + main.count(">A normal post<")
    assert ">Pinned<" not in client.get("/?sort=old").text
    assert ">Pinned<" not in client.get("/?sort=views").text


def test_empty_state(client):
    body = client.get("/").text
    assert "No posts yet." in body
    assert "Sort by" in body


# -- tags ----------------------------------------------------------------


def test_normalise_tags():
    assert store.normalise_tags("#Berlin, HELP, berlin") == (["berlin", "help"], False)
    assert store.normalise_tags("a, b, c, d")[1] is True
    assert store.normalise_tags("!!, ok")[0] == ["ok"]
    assert store.normalise_tags("x" * 40)[0] == ["x" * 24]


def test_tag_page_lists_posts_with_that_tag(client, app, pass_id):
    make_post(app, pass_id, title="Berlin post", tags=["berlin"])
    make_post(app, pass_id, title="Other post", tags=["food"])
    body = client.get("/?tag=berlin").text
    titles = [line.strip() for line in body.splitlines() if 'class="title"' in line]
    assert any("Berlin post" in t for t in titles)
    assert not any("Other post" in t for t in titles)


def test_tag_menu_counts(app, pass_id):
    make_post(app, pass_id, tags=["berlin", "help"])
    make_post(app, pass_id, tags=["berlin"])
    assert store.tag_counts(app.conn)[0] == ("berlin", 2)


# -- search --------------------------------------------------------------


def test_search_finds_posts_and_comments(client, app, pass_id):
    post = make_post(app, pass_id, title="Housing in Berlin", text="Deposit trouble")
    make_comment(app, pass_id, post, text="the landlord ignored me")
    assert "Housing in Berlin" in client.get("/search?q=berlin").text
    assert "the landlord ignored me" in client.get("/search?q=landlord").text


def test_search_ignores_hidden_posts(client, app, pass_id):
    post = make_post(app, pass_id, title="Unlistable", text="flagbait")
    app.conn.execute("UPDATE item SET hidden = 1 WHERE id = ?", (post.id,))
    app.conn.commit()
    assert "Unlistable" not in client.get("/search?q=flagbait").text


def test_search_ignores_private_replies(client, app, pass_id):
    post = make_post(app, pass_id)
    make_comment(app, pass_id, post, text="secretconfession", private_to=store.create_pass(app.conn))
    results = client.get("/search?q=secretconfession").text
    assert 'class="title"' not in results.split("<main")[1].split("</main>")[0]


def test_search_rejects_fts_operators(client, app, pass_id):
    make_post(app, pass_id, title="Plain title")
    response = client.get('/search?q="unbalanced OR (')
    assert response.status_code == 200


def test_hash_search_redirects_to_the_tag(client, app, pass_id):
    make_post(app, pass_id, title="Tagged", tags=["berlin"])
    response = client.get("/search?q=%23berlin", follow_redirects=True)
    assert "Tagged" in response.text


def test_sort_links_reset_to_each_sorts_starting_page(client, app, pass_id):
    make_post(app, pass_id, title="Recent post")
    body = client.get("/?before=2020-01-10").text
    assert 'href="/?sort=old"' in body
    assert 'href="/?sort=views"' in body
