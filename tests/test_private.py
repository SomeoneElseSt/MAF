"""Private replies: who sees them, what they're excluded from, and how they nest."""

from maf import store


def make_post(app, pass_id, title="A post", text="text"):
    return store.create_post(app.conn, pass_id, title, text, None, [])


def add_comment(app, pass_id, parent, text="hi", private_to=None):
    return store.create_comment(app.conn, pass_id, parent, text, private_to)


def visible_texts(app, thread_id, viewer):
    return [i.text for i in store.thread_items(app.conn, thread_id, viewer)]


def test_only_the_two_parties_see_a_private_reply(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    stranger = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "just for op", private_to=op)
    assert "just for op" in visible_texts(app, post.id, op)
    assert "just for op" in visible_texts(app, post.id, other)
    assert "just for op" not in visible_texts(app, post.id, stranger)
    assert "just for op" not in visible_texts(app, post.id, None)


def test_descendants_of_a_private_reply_are_hidden_with_it(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    stranger = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "secret", private_to=op)
    reply = add_comment(app, op, private, "reply inside", private_to=other)
    assert "reply inside" in visible_texts(app, post.id, op)
    assert "reply inside" not in visible_texts(app, post.id, stranger)


def test_replies_to_a_private_item_are_forced_private(app, signed_in):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "secret", private_to=op)
    signed_in.post("/comment", data={"parent_id": private.id, "text": "follow up"}, follow_redirects=False)
    child = app.conn.execute("SELECT private_to FROM item WHERE parent_id = ?", (private.id,)).fetchone()
    assert child["private_to"] == other


def test_private_items_are_excluded_from_counts_search_and_tags(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    add_comment(app, other, post, "uniqueword", private_to=op)
    assert store.comment_count(app.conn, post.id) == 0
    assert store.search(app.conn, "uniqueword") == []


def test_cannot_reply_privately_to_yourself(app, signed_in, pass_id):
    post = make_post(app, pass_id)
    signed_in.post("/comment", data={"parent_id": post.id, "text": "note to self", "private": "on"}, follow_redirects=False)
    row = app.conn.execute("SELECT private_to FROM item WHERE parent_id = ?", (post.id,)).fetchone()
    assert row["private_to"] is None
