"""Dates: its own board, kept apart from the front page, with its own pinned posts and colour."""

from maf import cli, store


def _post(app, title, tags=("help",)):
    return store.create_post(app.conn, store.create_pass(app.conn), title, None, None, list(tags))


def _move(app, post_id, board):
    return cli.cmd_board(app.conn, type("Args", (), {"board": board, "id": post_id})())


def test_a_dates_post_leaves_the_front_page_hashtags_search_and_new(signed_in, app, pass_id):
    stays, moved = _post(app, "Front walrus", tags=("calm",)), _post(app, "Dates walrus", tags=("wild",))
    assert _move(app, f"https://example.org/thread/{moved.id}", "dates") == 0
    front = signed_in.get("/").text
    assert f'data-id="{stays.id}"' in front and f'data-id="{moved.id}"' not in front
    assert "Dates walrus" not in signed_in.get("/search?q=walrus").text
    assert [t for t, _ in store.tag_counts(app.conn)] == ["calm"]
    assert [p.id for p in store.new_activity(app.conn, pass_id, "2000-01-01T00:00:00Z")] == [stays.id]


def test_dates_shows_its_own_pins_and_not_the_front_pages(signed_in, app):
    front_pin, dates_pin = _post(app, "Front pin"), _post(app, "How Dates works")
    _move(app, dates_pin.id, "dates")
    store.set_pinned(app.conn, front_pin.id, True)
    store.set_pinned(app.conn, dates_pin.id, True)
    page = signed_in.get("/dates").text
    assert "How Dates works" in page and "Front pin" not in page
    assert "How Dates works" not in signed_in.get("/").text


def test_dates_has_its_colour_and_its_thread_keeps_it(signed_in, app):
    post = _post(app, "On dates")
    _move(app, post.id, "dates")
    for path in ("/dates", f"/thread/{post.id}"):
        assert 'data-board="dates"' in signed_in.get(path).text.split("<body", 1)[1].split(">", 1)[0]
    assert "data-board" not in signed_in.get("/").text.split("<body", 1)[1].split(">", 1)[0]


def test_the_header_link_goes_to_dates_and_toggles_back_from_it(signed_in):
    assert '<a class="dates-toggle" href="/dates">Dates</a>' in signed_in.get("/").text
    assert '<a class="dates-toggle" href="/?side=main" aria-current="page">Dates</a>' in signed_in.get("/dates").text  # toggles back


def test_dates_needs_signing_in(client):
    assert signed_out_redirects(client.get("/dates", follow_redirects=False))


def signed_out_redirects(response):
    return response.status_code in (302, 303, 307) and "/dates" not in response.headers.get("location", "/dates")


def test_moving_back_and_unknown_posts(app, capsys):
    post = _post(app, "Back and forth")
    assert _move(app, post.id, "dates") == 0 and store.get_item(app.conn, post.id).board == "dates"
    assert _move(app, post.id, "main") == 0 and store.get_item(app.conn, post.id).board == "main"
    assert _move(app, "no-such-post", "dates") == 1
    out = capsys.readouterr().out
    assert "Moved" in out and "Dates" in out and "front page" in out


def test_opening_dates_turns_nsfw_off(signed_in):
    signed_in.cookies.update({"maf_nsfw": "1"})
    response = signed_in.get("/dates")
    body_tag = response.text.split("<body", 1)[1].split(">", 1)[0]
    assert "data-nsfw" not in body_tag and "data-on>NSFW" not in response.text
    assert 'maf_nsfw=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]


def test_submit_on_dates_opens_the_profile_form(signed_in):
    dates = signed_in.get("/dates").text
    assert 'href="/dates/submit"' in dates
    form = signed_in.get("/dates/submit").text
    for name in ("region", "gender", "height", "city", "looking_for", "comment"):
        assert f'name="{name}"' in form
    assert 'name="title"' not in form and 'data-board="dates"' in form


def test_on_the_dates_form_the_logo_and_dates_lead_to_the_dates_home(signed_in):
    assert '<a class="dates-toggle" href="/dates">' in signed_in.get("/submit").text
    dates_form = signed_in.get("/dates/submit").text
    assert '<a class="brand" href="/dates">' in dates_form
    assert '<a class="dates-toggle" href="/dates" aria-current="page">' in dates_form
    assert '<a class="nsfw-toggle" href="/?side=nsfw">NSFW' in dates_form


def test_on_a_dates_post_nsfw_shows_its_state_and_leads_to_the_nsfw_home(signed_in, app):
    post = _post(app, "On dates")
    _move(app, post.id, "dates")
    signed_in.cookies.update({"maf_nsfw": "1"})
    page = signed_in.get(f"/thread/{post.id}").text
    assert 'data-board="dates"' in _body(page) and "data-nsfw" not in _body(page)
    assert 'href="/?side=nsfw" data-on>NSFW' in page  # lit up, and leads home to the NSFW side


def _body(page):
    return page.split("<body", 1)[1].split(">", 1)[0]


def test_dates_sorts_its_profiles(signed_in, app):
    older, newer = _post(app, "Older profile"), _post(app, "Newer profile")
    for post in (older, newer):
        _move(app, post.id, "dates")
    app.conn.execute("UPDATE item SET created_at = '2026-01-01T00:00:00Z' WHERE id = ?", (older.id,))
    app.conn.commit()
    newest_first = signed_in.get("/dates").text
    assert 'aria-current="true">Newest' in newest_first or "Sort by" in newest_first
    assert newest_first.index("Newer profile") < newest_first.index("Older profile")
    oldest_first = signed_in.get("/dates?sort=old").text
    assert oldest_first.index("Older profile") < oldest_first.index("Newer profile")


def test_the_logo_on_a_post_goes_home_to_its_board(signed_in, app):
    dates_post, spicy = _post(app, "On dates"), store.create_post(app.conn, store.create_pass(app.conn), "Spicy", None, None, ["help"], nsfw=True)
    _move(app, dates_post.id, "dates")
    assert '<a class="brand" href="/dates">' in signed_in.get(f"/thread/{dates_post.id}").text
    assert '<a class="brand" href="/?side=nsfw">' in signed_in.get(f"/thread/{spicy.id}").text
    response = signed_in.get("/?side=nsfw", follow_redirects=False)
    assert response.status_code == 303 and "maf_nsfw=1" in response.headers["set-cookie"]
    assert "maf_nsfw=0" in signed_in.get("/?side=main", follow_redirects=False).headers["set-cookie"]


def test_on_a_dates_post_the_header_link_goes_to_the_dates_page(signed_in, app):
    post = _post(app, "On dates")
    _move(app, post.id, "dates")
    assert '<a class="dates-toggle" href="/dates" aria-current="page">' in signed_in.get(f"/thread/{post.id}").text


def test_a_pinned_dates_post_takes_normal_comments_and_a_profile_does_not(signed_in, app):
    note, profile = _post(app, "How Dates works"), _post(app, "Berlin: Woman, Europe, 160–175 cm")
    for post in (note, profile):
        _move(app, post.id, "dates")
    store.set_pinned(app.conn, note.id, True)
    store.create_comment(app.conn, store.create_pass(app.conn), store.get_item(app.conn, note.id), "Feedback", None)
    pinned_page = signed_in.get(f"/dates/thread/{note.id}").text
    assert 'id="comment-form"' in pinned_page and "Reply with profile" not in pinned_page
    assert 'class="match"' not in pinned_page and "match-dialog" not in pinned_page and ">Reply</a>" in pinned_page
    assert 'data-board="dates"' in _body(pinned_page)  # still the Dates colour
    profile_page = signed_in.get(f"/dates/thread/{profile.id}").text
    assert 'id="comment-form"' not in profile_page and "Reply with profile" in profile_page


def test_profile_replies_show_match_hide_sent_and_unmatch_without_flag(signed_in, app, pass_id):
    mine = _post_by(app, pass_id, "My profile")
    _move(app, mine.id, "dates")
    waiting, talking = store.create_pass(app.conn), store.create_pass(app.conn)
    store.create_comment(app.conn, waiting, mine, "Their profile", None)
    started = store.create_comment(app.conn, talking, mine, "Another profile", None)
    store.create_comment(app.conn, pass_id, started, "Hi", talking)
    owner_view = signed_in.get(f"/dates/thread/{mine.id}").text
    assert owner_view.count('class="match"') == 1 and owner_view.count('class="hide-profile"') == 1
    assert owner_view.count('class="unmatch"') == 1 and "Flag</button>" not in owner_view
    theirs = _post(app, "Their profile post")
    _move(app, theirs.id, "dates")
    store.create_comment(app.conn, pass_id, store.get_item(app.conn, theirs.id), "My profile", None)
    sender_view = signed_in.get(f"/dates/thread/{theirs.id}").text
    assert 'class="sent"' not in sender_view and 'aria-controls="delete-' in sender_view


def _post_by(app, pass_id, title):
    return store.create_post(app.conn, pass_id, title, None, None, ["help"])


def test_profiles_have_no_reactions_but_pinned_dates_posts_do(signed_in, app):
    note, profile = _post(app, "How Dates works"), _post(app, "A profile")
    for post in (note, profile):
        _move(app, post.id, "dates")
    store.set_pinned(app.conn, note.id, True)
    assert "react-add" in signed_in.get(f"/dates/thread/{note.id}").text
    assert "react-add" not in signed_in.get(f"/dates/thread/{profile.id}").text


def test_replies_inside_a_match_say_who_can_see_them_and_are_always_private(signed_in, app, pass_id):
    mine = _post_by(app, pass_id, "My profile")
    _move(app, mine.id, "dates")
    started = store.create_comment(app.conn, store.create_pass(app.conn), mine, "Their profile", None)
    store.create_comment(app.conn, pass_id, started, "Hi", started.pass_id)
    page = signed_in.get(f"/dates/thread/{mine.id}").text
    assert "Only visible to " in page and "Make only visible to" not in page
    assert 'data-always-private' in page and '<input type="hidden" name="private" value="on">' in page


def test_your_profile_counts_its_replies_above_a_line(signed_in, app, pass_id):
    mine = _post_by(app, pass_id, "My profile")
    _move(app, mine.id, "dates")
    page = signed_in.get(f"/dates/thread/{mine.id}").text
    assert "profile-replies-count" not in page  # nothing to count yet
    for _ in range(2):
        store.create_comment(app.conn, store.create_pass(app.conn), mine, "A profile", None)
    page = signed_in.get(f"/dates/thread/{mine.id}").text
    assert '<p class="profile-replies-count">2 people replied with their profiles</p>' in page
    assert 'class="comments profile-replies"' in page


def test_a_match_box_waits_until_the_other_person_has_a_device_key(signed_in, app, pass_id):
    mine = _post_by(app, pass_id, "My profile")
    _move(app, mine.id, "dates")
    them = store.create_pass(app.conn)
    store.create_comment(app.conn, them, mine, "Their profile", None)
    page = signed_in.get(f"/dates/thread/{mine.id}").text
    assert "once they open this thread on their device" in page
    app.conn.execute("INSERT INTO thread_key (pass_id, thread_id, public_key) VALUES (?, ?, 'k')", (them, mine.id))
    app.conn.commit()
    assert "once they open this thread on their device" not in signed_in.get(f"/dates/thread/{mine.id}").text


def test_saving_on_a_dates_thread_comes_back_to_its_dates_address(signed_in, app, pass_id):
    note = _post(app, "How Dates works")
    _move(app, note.id, "dates")
    store.set_pinned(app.conn, note.id, True)
    mine = store.create_comment(app.conn, pass_id, store.get_item(app.conn, note.id), "First words", None)
    response = signed_in.post("/edit", data={"item_id": mine.id, "thread_id": note.id, "text": "Better words"}, follow_redirects=False)
    assert response.headers["location"] == f"/dates/thread/{note.id}#{mine.id}"


ANSWERS = {"region": "Europe", "gender": "Woman", "height": "Under 5′3″ (160 cm)", "city": "Berlin",
           "looking_for": "Friend", "comment": "Film and long walks."}


def test_a_profile_is_written_and_read_back_the_same_way():
    from maf import profiles
    assert profiles.title_of(ANSWERS) == "Berlin: Woman, Europe, under 160 cm"
    assert profiles.values_of(profiles.text_of(ANSWERS)) == ANSWERS
    assert profiles.missing({**ANSWERS, "city": "Paris"}) == {"city": "Pick one."}


def test_your_profile_is_edited_through_its_form(signed_in, app, pass_id):
    from maf import profiles
    mine = store.create_post(app.conn, pass_id, profiles.title_of(ANSWERS), profiles.text_of(ANSWERS), None, [])
    _move(app, mine.id, "dates")
    page = signed_in.get(f"/dates/thread/{mine.id}").text
    assert '<a class="button" href="/dates/edit">Edit profile</a>' in page and f'id="edit-{mine.id}"' not in page
    assert signed_in.get("/dates/submit", follow_redirects=False).headers["location"] == "/dates/edit"
    form = signed_in.get("/dates/edit").text
    assert "Edit your profile" in form and "Film and long walks." in form and 'value="Berlin"' in form
    assert 'id="delete-dialog"' in form


def test_after_sending_your_profile_the_button_says_replied(signed_in, app, pass_id):
    theirs = _post(app, "Their profile")
    _move(app, theirs.id, "dates")
    assert "data-send-profile" in signed_in.get(f"/dates/thread/{theirs.id}").text or "need-profile" in signed_in.get(f"/dates/thread/{theirs.id}").text
    store.create_comment(app.conn, pass_id, store.get_item(app.conn, theirs.id), "My profile", None)
    page = signed_in.get(f"/dates/thread/{theirs.id}").text
    assert ">Replied</button>" in page and "Reply with profile" not in page


def test_the_feed_says_when_someone_sends_their_profile_and_when_they_match(app, pass_id):
    mine = _post_by(app, pass_id, "My profile")
    _move(app, mine.id, "dates")
    them = store.create_pass(app.conn)
    store.create_comment(app.conn, them, mine, "Their profile", None)
    theirs = _post_by(app, them, "Their profile post")
    _move(app, theirs.id, "dates")
    sent = store.create_comment(app.conn, pass_id, store.get_item(app.conn, theirs.id), "My profile", None)
    first = store.create_comment(app.conn, them, sent, "Hi!", pass_id)
    hello = store.create_comment(app.conn, pass_id, first, "Hello", them)
    store.create_comment(app.conn, them, hello, "Friday?", pass_id)
    labels = [n["label"] for n in store.notifications(app.conn, pass_id)]
    assert sorted(labels) == sorted(["Someone replied with their profile", "Someone matched with you", "New message from your match"])


PROFILE_FORM = {"region": "Europe", "gender": "Woman", "height": "5′3″–5′9″ (160–175 cm)", "city": "Berlin",
           "looking_for": "Friend", "comment": "Coffee first."}


def test_posting_a_profile_puts_it_on_dates_and_a_second_post_edits_it(signed_in, app, pass_id):
    response = signed_in.post("/dates/submit", data={**PROFILE_FORM, "can_encrypt": "1"}, follow_redirects=False)
    profile = store.own_profile(app.conn, pass_id)
    assert response.status_code == 303 and response.headers["location"] == f"/dates/thread/{profile.id}"
    assert profile.board == "dates" and profile.title == "Berlin: Woman, Europe, 160–175 cm"
    signed_in.post("/dates/submit", data={**PROFILE_FORM, "can_encrypt": "1", "city": "Tokyo"})
    assert store.own_profile(app.conn, pass_id).id == profile.id
    assert store.get_item(app.conn, profile.id).title.startswith("Tokyo:")


def test_a_profile_with_a_question_left_blank_says_pick_one(signed_in, app, pass_id):
    response = signed_in.post("/dates/submit", data={**PROFILE_FORM, "can_encrypt": "1", "gender": ""})
    assert response.status_code == 400 and "Pick one." in response.text and 'value="Berlin"' in response.text
    assert store.own_profile(app.conn, pass_id) is None


def test_deleting_your_profile_takes_its_thread_with_it(signed_in, app, pass_id):
    signed_in.post("/dates/submit", data={**PROFILE_FORM, "can_encrypt": "1"})
    profile = store.own_profile(app.conn, pass_id)
    reply = store.create_comment(app.conn, store.create_pass(app.conn), profile, None, pass_id, sealed="x")
    response = signed_in.post("/dates/delete", follow_redirects=False)
    assert response.headers["location"] == "/dates"
    assert store.get_item(app.conn, profile.id) is None and store.get_item(app.conn, reply.id) is None


def test_a_browser_that_cant_encrypt_cant_post_a_profile(signed_in, app, pass_id):
    response = signed_in.post("/dates/submit", data=PROFILE_FORM)
    assert response.status_code == 400 and "support JavaScript" in response.text
    assert store.own_profile(app.conn, pass_id) is None
