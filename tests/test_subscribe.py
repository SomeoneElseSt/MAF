"""Subscribe: following a whole post, and its activity arriving in the Feed."""

from maf import store


def make_post(app, pass_id, title="A post", text="Some text"):
    return store.create_post(app.conn, pass_id, title, text, None, [])


def test_subscribe_follows_and_unsubscribes(signed_in, app, pass_id):
    post = make_post(app, pass_id)
    signed_in.post("/subscribe", data={"thread_id": post.id})
    assert store.is_subscribed(app.conn, pass_id, post.id)
    assert store.subscribers(app.conn, post.id) == [pass_id]
    page = signed_in.get(f"/thread/{post.id}").text
    assert ">Unsubscribe</button>" in page
    signed_in.post("/subscribe", data={"thread_id": post.id})
    assert not store.is_subscribed(app.conn, pass_id, post.id)
    assert ">Subscribe</button>" in signed_in.get(f"/thread/{post.id}").text


def test_subscribe_button_sits_next_to_comment(signed_in, app, pass_id):
    post = make_post(app, pass_id)
    page = signed_in.get(f"/thread/{post.id}").text
    comment = page.index("data-needs-text>Comment</button>")
    subscribe = page.index("form=\"subscribe-form\">Subscribe</button>")
    assert 0 < subscribe - comment < 200


def test_a_reply_on_a_subscribed_post_reaches_the_feed(signed_in, app, pass_id):
    author = store.create_pass(app.conn)
    post = make_post(app, author)
    signed_in.post("/subscribe", data={"thread_id": post.id})
    reply = store.create_comment(app.conn, author, post, "an answer", None)
    items = store.notifications(app.conn, pass_id)
    activity = [n for n in items if n["kind"] == "activity"]
    assert activity and activity[0]["url"] == f"/thread/{post.id}#{reply.id}"
    page = signed_in.get("/notifications").text
    assert "New activity on a post you subscribed to" in page


def test_your_own_activity_is_not_in_the_feed(signed_in, app, pass_id):
    post = make_post(app, store.create_pass(app.conn))
    signed_in.post("/subscribe", data={"thread_id": post.id})
    store.create_comment(app.conn, pass_id, post, "my own words", None)
    assert [n for n in store.notifications(app.conn, pass_id) if n["kind"] == "activity"] == []


def test_nothing_arrives_without_subscribing(signed_in, app, pass_id):
    author = store.create_pass(app.conn)
    post = make_post(app, author)
    store.create_comment(app.conn, author, post, "an answer", None)
    assert [n for n in store.notifications(app.conn, pass_id) if n["kind"] == "activity"] == []


def test_an_unlisted_post_cannot_be_subscribed_to(signed_in, app, pass_id):
    post = make_post(app, pass_id)
    app.conn.execute("UPDATE item SET hidden = 1 WHERE id = ?", (post.id,))
    app.conn.commit()
    signed_in.post("/subscribe", data={"thread_id": post.id})
    assert not store.is_subscribed(app.conn, pass_id, post.id)


def test_deleting_a_post_drops_its_subscriptions(app, pass_id):
    post = make_post(app, pass_id)
    store.set_subscribed(app.conn, pass_id, post.id, True)
    store.delete_item(app.conn, post.id)
    assert app.conn.execute("SELECT COUNT(*) AS n FROM subscription").fetchone()["n"] == 0
