"""Emoji reactions and the developer API."""

from maf import store
from maf.emoji import PICKER_EMOJI
from maf.util import sha256_hex


def make_post(app, pass_id, title="A post"):
    return store.create_post(app.conn, pass_id, title, "text", None, [])


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# -- reactions -----------------------------------------------------------


def test_toggle_adds_and_removes(app, pass_id):
    post = make_post(app, pass_id)
    assert store.toggle_reaction(app.conn, pass_id, post.id, "👍")
    counts, mine = store.reaction_summary(app.conn, post.id, pass_id)
    assert counts == {"👍": 1} and mine == {"👍"}
    assert not store.toggle_reaction(app.conn, pass_id, post.id, "👍")
    assert store.reaction_summary(app.conn, post.id, pass_id)[0] == {}


def test_counts_aggregate_across_passes(app, pass_id):
    post = make_post(app, pass_id)
    other = store.create_pass(app.conn)
    store.toggle_reaction(app.conn, pass_id, post.id, "🔥")
    store.toggle_reaction(app.conn, other, post.id, "🔥")
    counts, _ = store.reaction_summary(app.conn, post.id, pass_id)
    assert counts == {"🔥": 2}


def test_route_toggles_a_reaction(viewer, app):
    post = make_post(app, viewer["pass_id"])
    viewer["client"].post("/react", data={"item_id": post.id, "emoji": "🎉"}, follow_redirects=False)
    assert store.reaction_summary(app.conn, post.id, viewer["pass_id"])[0] == {"🎉": 1}


def test_route_rejects_emoji_outside_the_set(viewer, app):
    post = make_post(app, viewer["pass_id"])
    viewer["client"].post("/react", data={"item_id": post.id, "emoji": "🦄"}, follow_redirects=False)
    assert store.reaction_summary(app.conn, post.id, viewer["pass_id"])[0] == {}


def test_the_set_has_24_unique_emoji():
    assert len(PICKER_EMOJI) == 24
    assert len(set(PICKER_EMOJI)) == 24
    assert {"👍", "👎", "😡"} <= set(PICKER_EMOJI)


def test_rate_limit_is_60_per_minute(app, pass_id):
    for _ in range(60):
        assert app.memory.allow(f"react:{pass_id}", 60)
    assert not app.memory.allow(f"react:{pass_id}", 60)


# -- API -----------------------------------------------------------------


def make_token(app, pass_id) -> str:
    token = "test-token-" + pass_id
    store.create_api_token(app.conn, sha256_hex(token), pass_id, token[-4:])
    return token


def test_api_requires_a_token(client):
    assert client.get("/api/v1/posts").status_code == 401
    assert client.get("/api/v1/posts", headers=bearer("nope")).status_code == 401


def test_api_lists_posts(client, app, pass_id):
    make_post(app, pass_id, title="API post")
    token = make_token(app, pass_id)
    body = client.get("/api/v1/posts", headers=bearer(token)).json()
    titles = [p["title"] for p in body["posts"]]
    assert "API post" in titles
    assert set(body["posts"][0]) == {
        "id", "title", "url", "text_preview", "created_at", "edited_at", "comment_count", "score", "views", "tags", "pinned",
    }


def test_api_excludes_hidden_posts(client, app, pass_id):
    post = make_post(app, pass_id, title="Hidden from API")
    app.conn.execute("UPDATE item SET hidden = 1 WHERE id = ?", (post.id,))
    app.conn.commit()
    body = client.get("/api/v1/posts", headers=bearer(make_token(app, pass_id))).json()
    assert "Hidden from API" not in [p["title"] for p in body["posts"]]


def test_api_thread_has_labels_and_op(client, app, pass_id):
    post = make_post(app, pass_id)
    store.create_comment(app.conn, pass_id, post, "hello", None)
    body = client.get(f"/api/v1/threads/{post.id}", headers=bearer(make_token(app, pass_id))).json()
    assert body["op"] is True
    assert body["author_id"] == app.labeler.label(pass_id, post.id)
    assert body["comments"][0]["author_id"] == body["author_id"]
    assert body["comments"][0]["op"] is True


def test_api_thread_omits_private_replies(client, app, pass_id):
    post = make_post(app, pass_id)
    recipient = store.create_pass(app.conn)
    store.create_comment(app.conn, pass_id, post, "private words", recipient)
    body = client.get(f"/api/v1/threads/{post.id}", headers=bearer(make_token(app, pass_id))).json()
    assert body["comments"] == []


def test_api_unknown_item_is_404(client, app, pass_id):
    assert client.get("/api/v1/threads/nope", headers=bearer(make_token(app, pass_id))).status_code == 404


def test_api_search_and_tags(client, app, pass_id):
    post = make_post(app, pass_id, title="Searchable post")
    app.conn.execute("INSERT INTO item_tag (item_id, tag) VALUES (?, 'berlin')", (post.id,))
    app.conn.commit()
    token = make_token(app, pass_id)
    assert client.get("/api/v1/search?q=searchable", headers=bearer(token)).json()["results"]
    tags = client.get("/api/v1/tags", headers=bearer(token)).json()["tags"]
    assert {"tag": "berlin", "count": 1} in tags


def test_api_rate_limit(app, pass_id):
    key = f"api:{pass_id}"
    for _ in range(60):
        assert app.memory.allow(key, 60)
    assert not app.memory.allow(key, 60)


def test_api_tokens_are_listed_by_last_four_and_revocable(viewer, app):
    pass_id = viewer["pass_id"]
    token = make_token(app, pass_id)
    listed = store.list_api_tokens(app.conn, pass_id)
    assert listed[0]["last4"] == token[-4:]
    assert not listed[0]["hash"] == token  # only the hash is stored
    assert store.revoke_api_token(app.conn, listed[0]["hash"], pass_id)
    assert store.list_api_tokens(app.conn, pass_id) == []


def test_new_token_is_shown_once_and_never_put_in_a_url(signed_in):
    response = signed_in.post("/tokens", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/guide/use-this-data"
    shown = signed_in.get("/guide/use-this-data").text
    assert "only shown once" in shown
    reloaded = signed_in.get("/guide/use-this-data").text
    assert "only shown once" not in reloaded
    assert reloaded.count('class="token-row"') == 1, "reloading must not create more tokens"


def test_tokens_are_capped_at_five_and_the_button_greys_out(signed_in, app):
    for _ in range(7):
        signed_in.post("/tokens")
    page = signed_in.get("/guide/use-this-data").text
    assert page.count('class="token-row"') == 5
    assert "disabled" in page and "Revoke one to create another" in page


def test_a_reaction_pings_pages_watching_its_thread(client, app, pass_id):
    from tests.conftest import sign_in_as

    post = make_post(app, pass_id)
    watching = app.live.subscribe(post.id)
    sign_in_as(client, app, pass_id).post("/react", data={"item_id": post.id, "emoji": "👍"}, follow_redirects=False)
    assert watching.qsize() == 1


def test_heart_on_fire_is_a_reaction_and_coffee_is_gone(client, app, pass_id):
    from tests.conftest import sign_in_as

    post = make_post(app, pass_id)
    viewer = sign_in_as(client, app, pass_id)
    viewer.post("/react", data={"item_id": post.id, "emoji": "❤️‍🔥"}, follow_redirects=False)
    viewer.post("/react", data={"item_id": post.id, "emoji": "☕"}, follow_redirects=False)
    counts, _ = store.reaction_summary(app.conn, post.id, pass_id)
    assert counts == {"❤️‍🔥": 1}
