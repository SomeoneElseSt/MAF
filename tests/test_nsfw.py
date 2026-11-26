"""NSFW: posts marked NSFW show only to browsers with NSFW on, and the rest only with it off."""

from maf import cli, store

NSFW_ON = {"maf_nsfw": "1"}


def _post(app, title, nsfw, tags=("help",)):
    return store.create_post(app.conn, store.create_pass(app.conn), title, None, None, list(tags), nsfw=nsfw)


def test_submitting_needs_an_answer_to_is_nsfw(signed_in):
    response = signed_in.post("/submit", data={"title": "No answer"})
    assert response.status_code == 400 and "Choose Yes or No." in response.text


def test_the_answer_is_kept_as_where_it_shows_and_what_was_answered(signed_in, app):
    response = signed_in.post("/submit", data={"title": "Spicy", "nsfw": "Yes"}, follow_redirects=False)
    assert response.status_code == 303
    post = store.get_item(app.conn, response.headers["location"].rsplit("/", 1)[-1])
    assert post.nsfw == 1 and post.nsfw_marked == 1


def test_each_side_lists_only_its_own_posts(signed_in, app):
    normal = _post(app, "About the library", nsfw=False)
    spicy = _post(app, "About something else", nsfw=True)
    off = signed_in.get("/").text
    assert f'data-id="{normal.id}"' in off and f'data-id="{spicy.id}"' not in off
    signed_in.cookies.update(NSFW_ON)
    on = signed_in.get("/").text
    assert f'data-id="{spicy.id}"' in on and f'data-id="{normal.id}"' not in on


def test_hashtags_search_and_the_hashtag_menu_follow_the_side(signed_in, app):
    _post(app, "Quiet walrus", nsfw=False, tags=("calm",))
    spicy = _post(app, "Loud walrus", nsfw=True, tags=("wild",))
    store.create_comment(app.conn, store.create_pass(app.conn), spicy, "walrus reply", None)
    assert "Loud walrus" not in signed_in.get("/?tag=wild").text
    off = signed_in.get("/search?q=walrus").text
    assert "Quiet walrus" in off and "Loud walrus" not in off and "walrus reply" not in off
    assert [t for t, _ in store.tag_counts(app.conn)] == ["calm"]
    signed_in.cookies.update(NSFW_ON)
    on = signed_in.get("/search?q=walrus").text
    assert "Loud walrus" in on and "walrus reply" in on and "Quiet walrus" not in on
    assert [t for t, _ in store.tag_counts(app.conn, nsfw=True)] == ["wild"]


def test_the_new_section_follows_the_side(app, pass_id):
    since = "2000-01-01T00:00:00Z"
    normal, spicy = _post(app, "Normal", nsfw=False), _post(app, "Spicy", nsfw=True)
    assert [p.id for p in store.new_activity(app.conn, pass_id, since)] == [normal.id]
    assert [p.id for p in store.new_activity(app.conn, pass_id, since, nsfw=True)] == [spicy.id]


def test_a_direct_link_opens_from_either_side(signed_in, app):
    spicy = _post(app, "Linked from a chat", nsfw=True)
    assert signed_in.get(f"/thread/{spicy.id}").status_code == 200


def test_the_header_switch_shows_the_side_youre_on(signed_in):
    off = signed_in.get("/").text
    assert 'class="nsfw-toggle" type="button" aria-pressed="false"' in off and 'id="nsfw-dialog"' in off
    assert "data-nsfw" not in off.split("<body", 1)[1].split(">", 1)[0]
    signed_in.cookies.update(NSFW_ON)
    on = signed_in.get("/").text
    assert 'aria-pressed="true">NSFW' in on and "data-nsfw" in on.split("<body", 1)[1].split(">", 1)[0]


def test_posting_starts_at_no_with_nsfw_off_and_yes_with_it_on(signed_in):
    assert 'value="No"' in signed_in.get("/submit").text.split('id="nsfw"', 1)[1].split(">", 1)[0]
    signed_in.cookies.update(NSFW_ON)
    assert 'value="Yes"' in signed_in.get("/submit").text.split('id="nsfw"', 1)[1].split(">", 1)[0]


def test_the_name_warning_keeps_the_answer_for_post_anyway(app, signed_in):
    app.name_filter.finds_name = lambda *texts: True
    body = signed_in.post("/submit", data={"title": "Names", "nsfw": "Yes"}).text
    assert '<input type="hidden" name="nsfw" value="Yes">' in body


def test_moving_a_post_keeps_what_its_author_answered(app, capsys):
    post = _post(app, "Marked normal", nsfw=False)
    assert cli.cmd_nsfw(app.conn, type("Args", (), {"id": f"https://example.org/thread/{post.id}"})(), True) == 0
    moved = store.get_item(app.conn, post.id)
    assert moved.nsfw == 1 and moved.nsfw_marked == 0  # a correction: shown as NSFW, answered No
    assert cli.cmd_nsfw(app.conn, type("Args", (), {"id": "no-such-post"})(), True) == 1
    assert "Moved" in capsys.readouterr().out


def test_phones_get_short_dates(signed_in, app):
    _post(app, "Any", nsfw=False)
    page = signed_in.get("/").text
    assert 'class="long-date"' in page and 'class="short-date"' in page
