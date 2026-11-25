"""The notification bell: replies and reactions to your posts and replies, and nothing else."""

from maf import store


def _setup(app):
    me, other, third = (store.create_pass(app.conn) for _ in range(3))
    post = store.create_post(app.conn, me, "My post", "text", None, [])
    return me, other, third, post


def test_replies_to_your_post_and_to_your_reply_show_up(app):
    me, other, _, post = _setup(app)
    mine = store.create_comment(app.conn, me, post, "my reply somewhere", None)
    their_post = store.create_post(app.conn, other, "Their post", "text", None, [])
    my_reply_there = store.create_comment(app.conn, me, their_post, "a thought of mine", None)
    a = store.create_comment(app.conn, other, post, "on your post", None)
    b = store.create_comment(app.conn, other, my_reply_there, "on your reply", None)
    found = {n["url"]: n for n in store.notifications(app.conn, me)}
    assert found[f"/thread/{post.id}#{a.id}"]["on"] == "post"
    assert found[f"/thread/{their_post.id}#{b.id}"] == {**found[f"/thread/{their_post.id}#{b.id}"], "on": "comment",
                                                        "about": "a thought of mine"}
    assert all(mine.id not in url for url in found)  # your own reply is never news to you


def test_your_own_activity_and_others_private_replies_dont_show_up(app):
    me, other, third, post = _setup(app)
    store.create_comment(app.conn, me, post, "replying to myself", None)
    their = store.create_comment(app.conn, third, post, "third's reply", None)
    store.create_comment(app.conn, other, their, "private to third", third)
    store.toggle_reaction(app.conn, me, post.id, "👍")
    urls = [n["url"] for n in store.notifications(app.conn, me)]
    assert urls == [f"/thread/{post.id}#{their.id}"]


def test_a_private_reply_to_you_shows_up_for_you(app):
    me, other, _, post = _setup(app)
    private = store.create_comment(app.conn, other, post, None, me, sealed='{"v":1}')
    assert [n["url"] for n in store.notifications(app.conn, me)] == [f"/thread/{post.id}#{private.id}"]


def test_reactions_are_grouped_per_post_or_reply_with_each_time(app):
    me, other, third, post = _setup(app)
    store.toggle_reaction(app.conn, other, post.id, "👍")
    store.toggle_reaction(app.conn, third, post.id, "❤️")
    store.toggle_reaction(app.conn, third, post.id, "👍")
    [group] = store.notifications(app.conn, me)
    assert group["kind"] == "reactions" and group["url"] == f"/thread/{post.id}"
    assert len(group["times"]) == 3 and set(group["emoji"]) == {"👍", "❤️"}


def test_removed_and_old_reactions_dont_show_up(app):
    me, other, _, post = _setup(app)
    removed = store.create_comment(app.conn, other, post, "named someone", None)
    store.remove_comment(app.conn, removed.id, "Removed because it named someone.")
    app.conn.execute("INSERT INTO reaction (pass_id, item_id, emoji) VALUES (?, ?, ?)", (other, post.id, "👍"))
    app.conn.commit()
    assert store.notifications(app.conn, me) == []


def test_the_bell_list_needs_sign_in_and_renders(app, client, signed_in, pass_id):
    from starlette.testclient import TestClient

    signed_out = TestClient(client.app).get("/notifications.json", follow_redirects=False)
    assert signed_out.status_code in (303, 401) and "items" not in signed_out.text
    post = store.create_post(app.conn, pass_id, "Mine", "text", None, [])
    store.create_comment(app.conn, store.create_pass(app.conn), post, "hello", None)
    data = signed_in.get("/notifications.json").json()
    assert data["items"][0]["kind"] == "reply"
    page = signed_in.get("/notifications").text
    assert "New reply to your post" in page and "“Mine”" in page
    assert 'class="bell"' in signed_in.get("/").text
