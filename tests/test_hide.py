"""maf hide: the maintainer hides a post or reply with a reason shown in its place; maf unhide undoes it."""

from maf import cli, store


def _hide(app, address, reason=cli.DEFAULT_HIDE_REASON):
    return cli.cmd_hide(app.conn, type("Args", (), {"id": address, "reason": reason})())


def _thread(app):
    post = store.create_post(app.conn, store.create_pass(app.conn), "A thread", None, None, ["help"])
    reply = store.create_comment(app.conn, store.create_pass(app.conn), post, "secret words here", None)
    return post, reply


def test_a_hidden_reply_shows_the_reason_instead_of_its_words(signed_in, app):
    post, reply = _thread(app)
    assert _hide(app, f"https://example.org/thread/{post.id}#reply-{reply.id}") == 0
    page = signed_in.get(f"/thread/{post.id}").text
    assert "secret words here" not in page and "Hidden because it mentioned someone." in page
    assert "in review after 5 flags" not in page


def test_unhide_brings_it_back_and_unflagging_doesnt(signed_in, app):
    post, reply = _thread(app)
    flagger = store.create_pass(app.conn)
    store.add_flag(app.conn, flagger, reply.id)
    _hide(app, reply.id)
    store.remove_flag(app.conn, flagger, reply.id)
    assert store.get_item(app.conn, reply.id).unlisted
    assert cli.cmd_unhide(app.conn, type("Args", (), {"id": reply.id})()) == 0
    assert "secret words here" in signed_in.get(f"/thread/{post.id}").text


def test_a_hidden_post_leaves_the_list_and_says_why(signed_in, app):
    post, _ = _thread(app)
    _hide(app, f"https://example.org/thread/{post.id}", reason="Hidden for a test.")
    assert f'data-id="{post.id}"' not in signed_in.get("/").text
    assert "Hidden for a test. It's been unlisted." in signed_in.get(f"/thread/{post.id}").text


def test_hiding_nothing_says_so(app, capsys):
    assert _hide(app, "no-such-item") == 1
    assert "No item no-such-item" in capsys.readouterr().out


def test_hide_post_unlists_your_own_post_and_unhide_brings_it_back(signed_in, app, pass_id):
    post = store.create_post(app.conn, pass_id, "Mine to hide", None, "findable words", ["help"])
    store.create_comment(app.conn, store.create_pass(app.conn), post, "a reply", None)
    signed_in.post("/hide-post", data={"thread_id": post.id})
    assert f'data-id="{post.id}"' not in signed_in.get("/").text
    assert not store.search(app.conn, "findable") and not store.tagged_posts(app.conn, "help", "new")
    page = signed_in.get(f"/thread/{post.id}").text
    assert "You hid this post." in page and "Unhide Post" in page and "a reply" in page
    signed_in.post("/hide-post", data={"thread_id": post.id})
    assert f'data-id="{post.id}"' in signed_in.get("/").text


def test_only_the_author_can_hide_a_post(signed_in, app):
    post = store.create_post(app.conn, store.create_pass(app.conn), "Not mine", None, None, ["help"])
    assert "Hide Post" not in signed_in.get(f"/thread/{post.id}").text
    signed_in.post("/hide-post", data={"thread_id": post.id})
    assert not store.get_item(app.conn, post.id).author_hidden
