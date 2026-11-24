"""House tags, the submit form and the thread page."""

import pytest

from maf import store
from maf.housetags import (
    DEFAULT_SUBMIT_TEMPLATE,
    EXAMPLE_POST,
    HOUSE_TAGS,
    etiquette,
    is_hot,
    reply_placeholder,
    submit_placeholder,
)

# -- house tags ----------------------------------------------------------



@pytest.fixture
def client(starlette_app, app):
    """These pages are students-only, so the client here is signed in as a reader."""
    from starlette.testclient import TestClient

    from tests.conftest import sign_in_as

    return sign_in_as(TestClient(starlette_app), app, store.create_pass(app.conn))

def test_the_four_house_tags():
    assert set(HOUSE_TAGS) == {"hottakes", "help", "wondering", "confession"}


def test_only_hottakes_is_highlighted():
    assert [t for t, h in HOUSE_TAGS.items() if h["highlight"]] == ["hottakes"]
    assert is_hot(["academics", "hottakes"])
    assert not is_hot(["academics", "minerva"])


def test_etiquette_only_where_defined():
    assert etiquette(["hottakes"])[0] == "hottakes"
    assert etiquette(["help"]) is None
    assert etiquette(["minerva"]) is None
    assert etiquette(["hottakes", "confession"])[0] == "hottakes"


def test_submit_placeholder_picks_the_first_house_tag():
    assert submit_placeholder([]) == EXAMPLE_POST
    assert submit_placeholder(["minerva"]) == "\n".join(DEFAULT_SUBMIT_TEMPLATE)
    assert submit_placeholder(["minerva", "help"]) == "\n".join(HOUSE_TAGS["help"]["submit_template"])
    assert submit_placeholder(["confession", "help"]).endswith("Leave out details that could identify me or anyone else.")


def test_reply_placeholder():
    assert reply_placeholder([]) == "Write a reply"
    assert reply_placeholder(["hottakes"]).startswith("Write a reply. Ideally:\n- Which part")


# -- submit --------------------------------------------------------------


def test_submit_requires_sign_in(starlette_app):
    from starlette.testclient import TestClient

    response = TestClient(starlette_app).get("/submit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/sign-in"


def test_submit_creates_a_post(signed_in, app, pass_id):
    response = signed_in.post(
        "/submit",
        data={"title": "My title", "text": "My text", "tags": "#berlin, help"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    post = store.get_item(app.conn, response.headers["location"].rsplit("/", 1)[-1])
    assert post.title == "My title" and post.tags == ["berlin", "help"]


def test_submit_needs_a_title(signed_in):
    body = signed_in.post("/submit", data={"title": "", "text": ""}).text
    assert "Add a title." in body


def test_a_title_alone_is_a_post(signed_in, app):
    response = signed_in.post("/submit", data={"title": "Is the library open on Sundays?"}, follow_redirects=False)
    assert response.status_code == 303
    post = store.get_item(app.conn, response.headers["location"].rsplit("/", 1)[-1])
    assert post.title == "Is the library open on Sundays?" and post.text is None and post.url is None
    assert signed_in.get(response.headers["location"]).status_code == 200


def test_submit_rejects_a_bad_url(signed_in):
    body = signed_in.post("/submit", data={"title": "T", "url": "not a url"}).text
    assert "look like a web address" in body  # rendered HTML-escaped


def test_submit_rejects_more_than_three_tags(signed_in):
    body = signed_in.post("/submit", data={"title": "T", "text": "x", "tags": "a, b, c, d"}).text
    assert "Use at most 3 hashtags." in body


def test_submit_keeps_the_text_when_it_fails(signed_in):
    body = signed_in.post("/submit", data={"title": "", "text": "keep me please"}).text
    assert "keep me please" in body


def test_the_page_shows_the_placeholder_javascript(signed_in):
    body = signed_in.get("/submit").text
    assert "submit-templates" in body
    assert "Up to 3, separated by commas." in body


# -- thread page ---------------------------------------------------------


def test_thread_shows_post_comments_and_labels(client, app, pass_id):
    post = store.create_post(app.conn, pass_id, "Thread title", "Thread body", None, [])
    store.create_comment(app.conn, pass_id, post, "a nested comment", None)
    body = client.get(f"/thread/{post.id}").text
    assert "Thread title" in body and "Thread body" in body
    assert "a nested comment" in body
    assert app.labeler.label(pass_id, post.id) in body
    assert "(OP)" in body


def test_thread_404_for_missing_item(client):
    assert client.get("/thread/doesnotexist").status_code == 404


def test_hottakes_thread_shows_etiquette_and_class(client, app, pass_id):
    post = store.create_post(app.conn, pass_id, "Hot take", "text", None, ["hottakes"])
    body = client.get(f"/thread/{post.id}").text
    assert "hottakes-thread" in body
    assert "argue with the take, not the person" in body


def test_private_reply_is_hidden_from_other_viewers(client, app, pass_id):
    author = store.create_pass(app.conn)
    post = store.create_post(app.conn, author, "Post", "text", None, [])
    store.create_comment(app.conn, author, post, "only for author", pass_id)
    assert "only for author" not in client.get(f"/thread/{post.id}").text
    from tests.conftest import sign_in_as

    viewer = sign_in_as(client, app, pass_id)
    assert "only for author" in viewer.get(f"/thread/{post.id}").text
