"""Preview cards for replies that link to another MAF thread."""

from maf import embed, store


def make_post(app, pass_id, title="Linked post", text="First words of the post.", tags=()):
    return store.create_post(app.conn, pass_id, title, text, None, list(tags))


def reply_to(app, pass_id, text):
    post = make_post(app, pass_id, title="Host post", text="host")
    store.create_comment(app.conn, pass_id, post, text, None)
    return post


def test_a_thread_link_gets_a_card_with_its_details(app, pass_id):
    linked = make_post(app, pass_id, title="Where's the food?", text="Late night in Berlin.", tags=["berlin"])
    store.create_comment(app.conn, store.create_pass(app.conn), linked, "an answer", None)
    reply_to(app, pass_id, f"See https://maforum.net/thread/{linked.id}")
    cards = embed.embeds_in(app.conn, f"See https://maforum.net/thread/{linked.id}", app.labeler, linked.id, "maforum.net")
    assert len(cards) == 1
    card = cards[0]
    assert card.id == linked.id and card.title == "Where's the food?" and card.preview == "Late night in Berlin."
    assert card.tags == ["berlin"] and card.comment_count == 1 and card.label


def test_ids_with_digits_are_recognised(app):
    # Real ids mix letters and digits ("09z8623s806n").
    assert embed.thread_id_in("https://maforum.net/thread/09z8623s806n", "maforum.net") == "09z8623s806n"


def test_a_bare_id_link_counts_too(app, pass_id):
    linked = make_post(app, pass_id)
    assert embed.thread_id_in(f"/{linked.id}", "maforum.net") == linked.id
    assert embed.thread_id_in(f"https://maforum.net/thread/{linked.id}", "maforum.net") == linked.id


def test_other_sites_and_other_pages_get_no_card(app):
    assert embed.thread_id_in("https://elsewhere.com/thread/abc-def", "maforum.net") is None
    assert embed.thread_id_in("https://maforum.net/?tag=berlin", "maforum.net") is None
    assert embed.thread_id_in("https://maforum.net/thread/abc-def?notice=x", "maforum.net") is None
    assert embed.thread_id_in("/thread/abc-def", "maforum.net") == "abc-def"


def test_an_unlisted_or_private_post_gets_no_card(app, pass_id):
    unlisted = make_post(app, pass_id)
    app.conn.execute("UPDATE item SET hidden = 1 WHERE id = ?", (unlisted.id,))
    app.conn.commit()
    private = store.create_comment(app.conn, pass_id, unlisted, "secret", store.create_pass(app.conn))
    text = f"https://maforum.net/thread/{unlisted.id} https://maforum.net/thread/{private.id} https://maforum.net/thread/no-such-post"
    assert embed.embeds_in(app.conn, text, app.labeler, "thread", "maforum.net") == []


def test_at_most_three_cards_and_no_repeats(app, pass_id):
    ids = [make_post(app, pass_id, title=f"Post {n}").id for n in range(5)]
    text = " ".join(f"https://maforum.net/thread/{i}" for i in ids) + f" and again https://maforum.net/thread/{ids[0]}"
    cards = embed.embeds_in(app.conn, text, app.labeler, "thread", "maforum.net")
    assert [c.id for c in cards] == ids[:3]


def test_the_thread_page_shows_the_card(signed_in, app, pass_id):
    linked = make_post(app, pass_id, title="A linked thread", text="Its first words.")
    host = make_post(app, pass_id, title="Host")
    # The test app's site is localhost:8000, so that is the host a link must name to get a card.
    store.create_comment(app.conn, pass_id, host, f"read this http://localhost:8000/thread/{linked.id}", None)
    page = signed_in.get(f"/thread/{host.id}").text
    assert 'class="embed" href="/thread/' + linked.id + '"' in page
    assert "A linked thread" in page and "Its first words." in page
