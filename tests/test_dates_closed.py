"""Dates closed (the default; MAF_DATES=on opens it): every Dates page, form and post is a 404, nothing on it can
be answered or reacted to, and it leaves the Feed. The posts stay in the database, so opening it brings them back."""

import dataclasses

import pytest

from maf import store


@pytest.fixture
def settings(settings):
    return dataclasses.replace(settings, dates_open=False)


@pytest.fixture
def profile(app):
    owner = store.create_pass(app.conn)
    post = store.create_post(app.conn, owner, "A profile", "answers", None, [], board="dates")
    return post


def test_dates_pages_and_forms_are_gone(signed_in, profile):
    for path in ("/dates", "/dates/submit", "/dates/edit", f"/dates/thread/{profile.id}", f"/thread/{profile.id}"):
        assert signed_in.get(path, follow_redirects=True).status_code == 404, path
    for path in ("/dates/submit", "/dates/edit", "/dates/delete", "/dates/unmatch", "/dates/hide"):
        assert signed_in.post(path, data={}).status_code in (404, 405), path


def test_nothing_on_dates_can_be_answered_or_reacted_to(signed_in, app, profile):
    signed_in.post("/comment", data={"parent_id": profile.id, "thread_id": profile.id, "text": "hi"})
    signed_in.post("/react", data={"item_id": profile.id, "thread_id": profile.id, "emoji": "❤️"})
    signed_in.post("/subscribe", data={"thread_id": profile.id})
    assert store.comment_count(app.conn, profile.id) == 0
    assert app.conn.execute("SELECT COUNT(*) FROM reaction").fetchone()[0] == 0
    assert app.conn.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 0


def test_dates_leaves_the_feed_and_the_front_page_still_works(client, app, profile):
    from tests.conftest import sign_in_as

    sender = store.create_pass(app.conn)
    store.create_comment(app.conn, sender, profile, None, profile.pass_id, sealed="{}")
    assert store.notifications(app.conn, profile.pass_id) != []
    owner = sign_in_as(client, app, profile.pass_id)
    assert owner.get("/notifications.json").json()["items"] == []
    assert owner.get("/").status_code == 200
