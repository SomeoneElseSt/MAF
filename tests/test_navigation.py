"""Where the header's logo, Dates and NSFW lead (navigation.py), on every kind of page."""

from maf.navigation import header_links


def links(path, nsfw_on=False, dates_page=False, post_board=None, has_query=False):
    nav = header_links(path, has_query, nsfw_on, dates_page, post_board)
    return nav.logo, nav.dates, nav.nsfw


MAIN_HOME, NSFW_HOME, DATES_HOME = "/?side=main", "/?side=nsfw", "/dates"


def test_on_the_main_home_the_words_go_to_their_boards():
    assert links("/") == (MAIN_HOME, DATES_HOME, NSFW_HOME)


def test_on_the_nsfw_home_nsfw_and_the_logo_go_back_to_main():
    assert links("/", nsfw_on=True) == (MAIN_HOME, DATES_HOME, MAIN_HOME)


def test_on_the_dates_home_dates_and_the_logo_go_back_to_main():
    assert links("/dates", dates_page=True) == (MAIN_HOME, MAIN_HOME, NSFW_HOME)


def test_on_a_post_the_logo_goes_home_to_its_board_and_the_words_to_theirs():
    assert links("/thread/a", post_board="dates") == (DATES_HOME, DATES_HOME, NSFW_HOME)
    assert links("/thread/a", post_board="nsfw", nsfw_on=False) == (NSFW_HOME, DATES_HOME, NSFW_HOME)
    assert links("/thread/a", post_board="main", nsfw_on=True) == (MAIN_HOME, DATES_HOME, NSFW_HOME)


def test_elsewhere_the_logo_goes_home_to_the_board_youre_browsing():
    assert links("/search", nsfw_on=True, has_query=True) == (NSFW_HOME, DATES_HOME, NSFW_HOME)
    assert links("/", nsfw_on=True, has_query=True)[2] == NSFW_HOME  # a hashtag page isn't the NSFW home


def test_on_a_form_the_links_work_as_anywhere_on_that_board():
    assert links("/submit") == (MAIN_HOME, DATES_HOME, NSFW_HOME)
    assert links("/submit", nsfw_on=True) == (NSFW_HOME, DATES_HOME, NSFW_HOME)
    assert links("/dates/submit", dates_page=True) == (DATES_HOME, DATES_HOME, NSFW_HOME)


def test_submit_opens_the_form_for_the_board_youre_on():
    submit = lambda *args: header_links(*args).submit
    assert submit("/dates", False, False, True, None) == "/dates/submit"
    assert submit("/thread/a", False, False, False, "dates") == "/dates/submit"
    assert submit("/", False, True, False, None) == "/submit"  # NSFW side already on
    assert submit("/thread/a", False, False, False, "nsfw") == "/?side=nsfw&next=/submit"  # an NSFW post, switch off
    assert submit("/thread/a", False, True, False, "main") == "/?side=main&next=/submit"


def _post(app, title, nsfw=False):
    from maf import store
    return store.create_post(app.conn, store.create_pass(app.conn), title, None, None, ["help"], nsfw=nsfw)


def test_posts_live_under_their_board_and_other_addresses_redirect(signed_in, app):
    from maf import store
    normal, spicy, dates = _post(app, "Normal"), _post(app, "Spicy", nsfw=True), _post(app, "Profile")
    store.set_board(app.conn, dates.id, "dates")
    for post, address in ((normal, f"/thread/{normal.id}"), (spicy, f"/nsfw/thread/{spicy.id}"), (dates, f"/dates/thread/{dates.id}")):
        assert signed_in.get(address, follow_redirects=False).status_code == 200
        for wrong in {f"/thread/{post.id}", f"/nsfw/thread/{post.id}", f"/dates/thread/{post.id}"} - {address}:
            response = signed_in.get(wrong + "?notice=Hi", follow_redirects=False)
            assert response.status_code == 302 and response.headers["location"] == address + "?notice=Hi"


def test_lists_link_straight_to_a_posts_address(signed_in, app):
    from maf import store
    dates = _post(app, "Profile")
    store.set_board(app.conn, dates.id, "dates")
    assert f'href="/dates/thread/{dates.id}"' in signed_in.get("/dates").text
    spicy = _post(app, "Spicy", nsfw=True)
    signed_in.cookies.update({"maf_nsfw": "1"})
    assert f'href="/nsfw/thread/{spicy.id}"' in signed_in.get("/").text


def test_a_posts_hashtags_open_on_its_side(signed_in, app):
    spicy = _post(app, "Spicy", nsfw=True)
    page = signed_in.get(f"/nsfw/thread/{spicy.id}").text
    assert 'href="/?side=nsfw&amp;next=/%3Ftag%3Dhelp"' in page
    response = signed_in.get("/?side=nsfw&next=/%3Ftag%3Dhelp", follow_redirects=False)
    assert response.headers["location"] == "/?tag=help" and "maf_nsfw=1" in response.headers["set-cookie"]
