"""Thread forms sent in the background (replies.js): redirects come back as {"location": ...}."""


def _post(signed_in, app):
    signed_in.post("/submit", data={"title": "In place", "tags": "help"})
    return app.conn.execute("SELECT id FROM item WHERE title = 'In place'").fetchone()["id"]


def test_a_comment_sent_in_place_says_where_to_land(signed_in, app):
    post_id = _post(signed_in, app)
    response = signed_in.post("/comment", data={"parent_id": post_id, "thread_id": post_id, "text": "hi"},
                              headers={"X-MAF-In-Place": "1"}, follow_redirects=False)
    assert response.status_code == 200
    reply_id = app.conn.execute("SELECT id FROM item WHERE text = 'hi'").fetchone()["id"]
    assert response.json() == {"location": f"/thread/{post_id}#{reply_id}"}


def test_a_normal_form_post_still_redirects(signed_in, app):
    post_id = _post(signed_in, app)
    response = signed_in.post("/comment", data={"parent_id": post_id, "thread_id": post_id, "text": "hey"},
                              follow_redirects=False)
    assert response.status_code == 303


def test_a_post_edit_sent_in_place_lands_on_the_post(signed_in, app):
    post_id = _post(signed_in, app)
    response = signed_in.post("/edit", data={"item_id": post_id, "thread_id": post_id, "text": "more"},
                              headers={"X-MAF-In-Place": "1"}, follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == {"location": f"/thread/{post_id}#{post_id}"}


def test_subscribing_sent_in_place_lands_back_on_the_thread(signed_in, app):
    post_id = _post(signed_in, app)
    response = signed_in.post("/subscribe", data={"thread_id": post_id, "back": ""},
                              headers={"X-MAF-In-Place": "1"}, follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == {"location": f"/thread/{post_id}"}
    assert app.conn.execute("SELECT COUNT(*) FROM subscription").fetchone()[0] == 1


def test_every_post_form_on_the_thread_page_is_sent_in_place():
    from pathlib import Path
    script = (Path(__file__).parent.parent / "maf" / "static" / "replies.js").read_text()
    assert "form[method='post' i]:not([data-full-page])" in script
