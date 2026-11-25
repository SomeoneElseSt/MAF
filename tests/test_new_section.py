"""The front page's New section: the server's part (new.js decides, in the browser, what you've opened)."""

from maf import store

SINCE = "2026-11-20T00:00:00Z"
BEFORE = "2026-11-10T00:00:00Z"
AFTER = "2026-11-21T00:00:00Z"


def _ids(posts):
    return [p.id for p in posts]


def test_new_activity_has_posts_by_others_and_new_comments_by_others(app, pass_id):
    conn = app.conn
    other = store.create_pass(conn)
    new_post = store.create_post(conn, other, "New one", None, None, ["help"], created_at=AFTER)
    old_post = store.create_post(conn, other, "Old with a new comment", None, None, ["help"], created_at=BEFORE)
    store.create_comment(conn, other, old_post, "hi", None, created_at=AFTER)
    quiet = store.create_post(conn, other, "Old and quiet", None, None, ["help"], created_at=BEFORE)
    found = _ids(store.new_activity(conn, pass_id, SINCE))
    assert new_post.id in found and old_post.id in found and quiet.id not in found


def test_your_own_posts_and_comments_are_not_new_to_you(app, pass_id):
    conn = app.conn
    other = store.create_pass(conn)
    mine = store.create_post(conn, pass_id, "Mine", None, None, ["help"], created_at=AFTER)
    theirs = store.create_post(conn, other, "Theirs", None, None, ["help"], created_at=BEFORE)
    store.create_comment(conn, pass_id, theirs, "my comment", None, created_at=AFTER)
    assert _ids(store.new_activity(conn, pass_id, SINCE)) == []
    # Someone else commenting on your post is new.
    store.create_comment(conn, other, mine, "a reply", None, created_at=AFTER)
    assert _ids(store.new_activity(conn, pass_id, SINCE)) == [mine.id]


def test_private_replies_and_unlisted_posts_stay_out(app, pass_id):
    conn = app.conn
    other = store.create_pass(conn)
    post = store.create_post(conn, other, "Old", None, None, ["help"], created_at=BEFORE)
    store.create_comment(conn, other, post, None, pass_id, created_at=AFTER, sealed="blob")
    assert _ids(store.new_activity(conn, pass_id, SINCE)) == []
    hidden = store.create_post(conn, other, "Flagged", None, None, ["help"], created_at=AFTER)
    conn.execute("UPDATE item SET hidden = 1 WHERE id = ?", (hidden.id,))
    assert hidden.id not in _ids(store.new_activity(conn, pass_id, SINCE))


def test_the_endpoint_sends_rows_and_refuses_a_bad_time(signed_in, app):
    other = store.create_pass(app.conn)
    post = store.create_post(app.conn, other, "Old", None, None, ["help"], created_at=BEFORE)
    store.create_comment(app.conn, other, post, "hi", None, created_at=AFTER)
    page = signed_in.get(f"/new-activity?since={SINCE}").text
    assert f'data-id="{post.id}"' in page and f'data-latest-comment="{AFTER}"' in page
    assert signed_in.get("/new-activity?since=yesterday").status_code == 400


def test_front_page_marks_your_posts_and_leaves_your_comments_out_of_the_times(signed_in, app, pass_id):
    other = store.create_pass(app.conn)
    mine = store.create_post(app.conn, pass_id, "Mine", None, None, ["help"])
    theirs = store.create_post(app.conn, other, "Theirs", None, None, ["help"])
    store.create_comment(app.conn, pass_id, theirs, "only me so far", None)
    page = signed_in.get("/").text
    assert 'class="list new-list" hidden data-now="' in page and "new.js" in page
    mine_row = page.split(f'data-id="{mine.id}"')[1].split(">")[0]
    theirs_row = page.split(f'data-id="{theirs.id}"')[1].split(">")[0]
    assert "data-mine" in mine_row and "data-mine" not in theirs_row
    assert "data-latest-comment" not in theirs_row


def test_opening_a_post_tells_the_browser_when(signed_in, app):
    post = store.create_post(app.conn, store.create_pass(app.conn), "A post", None, None, ["help"])
    page = signed_in.get(f"/thread/{post.id}").text
    assert f'id="{post.id}" data-views=' in page and 'data-now="' in page and "new.js" in page
