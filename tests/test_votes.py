"""Up and down votes on posts."""

from maf import store


def make_post(app, pass_id, title="A post"):
    return store.create_post(app.conn, pass_id, title, "text", None, [])


def test_vote_toggles_and_switches(app, pass_id):
    post = make_post(app, pass_id)
    assert store.cast_vote(app.conn, pass_id, post.id, 1) == 1
    assert store.vote_scores(app.conn, [post.id]) == {post.id: 1}
    assert store.cast_vote(app.conn, pass_id, post.id, -1) == -1  # switching replaces, never stacks
    assert store.vote_scores(app.conn, [post.id]) == {post.id: -1}
    assert store.cast_vote(app.conn, pass_id, post.id, -1) == 0  # the same arrow again takes it back
    assert store.vote_scores(app.conn, [post.id]) == {}
    assert store.my_vote(app.conn, pass_id, post.id) == 0


def test_score_is_ups_minus_downs_across_passes(app, pass_id):
    post = make_post(app, pass_id)
    for value in (1, 1, 1, -1):
        store.cast_vote(app.conn, store.create_pass(app.conn), post.id, value)
    assert store.with_counts(app.conn, [post])[0].score == 2


def test_route_votes_and_fills_the_arrow(viewer, app):
    post = make_post(app, viewer["pass_id"])
    client = viewer["client"]
    client.post("/vote", data={"item_id": post.id, "thread_id": post.id, "value": "up"}, follow_redirects=False)
    assert store.my_vote(app.conn, viewer["pass_id"], post.id) == 1
    page = client.get(f"/thread/{post.id}").text
    assert 'class="vote-up" type="submit" aria-pressed="true"' in page
    assert 'class="vote-down" type="submit" aria-pressed="false"' in page
    assert '<span class="vote-score" aria-label="Score 1">1</span>' in page


def test_front_page_shows_the_score(viewer, app):
    post = make_post(app, viewer["pass_id"])
    store.cast_vote(app.conn, store.create_pass(app.conn), post.id, 1)
    assert "1 point," in viewer["client"].get("/").text


def test_route_rejects_bad_values_and_replies(viewer, app):
    post = make_post(app, viewer["pass_id"])
    reply = store.create_comment(app.conn, viewer["pass_id"], post, "a reply", None)
    client = viewer["client"]
    client.post("/vote", data={"item_id": post.id, "value": "sideways"}, follow_redirects=False)
    client.post("/vote", data={"item_id": reply.id, "value": "up"}, follow_redirects=False)
    assert store.vote_scores(app.conn, [post.id, reply.id]) == {}


def test_api_includes_the_score(app, pass_id):
    post = make_post(app, pass_id)
    store.cast_vote(app.conn, pass_id, post.id, -1)
    from maf import api
    assert api._post_json(store.with_counts(app.conn, [post])[0])["score"] == -1


def test_a_negative_score_is_not_shown(viewer, app):
    post = make_post(app, viewer["pass_id"])
    store.cast_vote(app.conn, store.create_pass(app.conn), post.id, -1)
    client = viewer["client"]
    assert 'class="vote-score"' not in client.get(f"/thread/{post.id}").text
    assert "-1 point" not in client.get("/").text
