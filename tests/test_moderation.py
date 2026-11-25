"""Flags, hiding, moderation requests and the maintainer CLI."""

from maf import store
from maf.cli import main as cli


def make_post(app, pass_id, title="A post"):
    return store.create_post(app.conn, pass_id, title, "text", None, [])


def flag_by(app, item_id, times=1):
    for _ in range(times):
        store.add_flag(app.conn, store.create_pass(app.conn), item_id)


# -- flags ---------------------------------------------------------------


def test_five_flags_hide_an_item(app, pass_id):
    post = make_post(app, pass_id)
    flag_by(app, post.id, 4)
    assert store.get_item(app.conn, post.id).hidden == 0
    flag_by(app, post.id)
    assert store.get_item(app.conn, post.id).hidden == 1


def test_one_flag_per_pass(app, pass_id):
    post = make_post(app, pass_id)
    assert store.add_flag(app.conn, pass_id, post.id)
    assert not store.add_flag(app.conn, pass_id, post.id)
    assert store.get_item(app.conn, post.id).flags == 1


def test_hidden_posts_leave_the_home_page_but_stay_reachable(signed_in, app, pass_id):
    client = signed_in
    post = make_post(app, pass_id, title="Hidden title")
    flag_by(app, post.id, 5)
    assert "Hidden title" not in client.get("/").text
    page = client.get(f"/thread/{post.id}")
    assert page.status_code == 200
    assert "Five people flagged this post" in page.text


def test_restored_items_can_never_be_hidden_again(app, pass_id):
    post = make_post(app, pass_id)
    flag_by(app, post.id, 5)
    store.unhide(app.conn, post.id)
    flag_by(app, post.id, 5)
    item = store.get_item(app.conn, post.id)
    assert item.hidden == 0 and item.restored == 1


# -- moderation requests -------------------------------------------------


def test_requests_are_deduped_per_pass_and_kind(app, pass_id):
    post = make_post(app, pass_id)
    assert store.add_moderation_request(app.conn, pass_id, post.id, "unhide")
    assert not store.add_moderation_request(app.conn, pass_id, post.id, "unhide")
    assert store.add_moderation_request(app.conn, pass_id, post.id, "nuke")
    assert store.request_counts(app.conn, post.id) == {"unhide": 1, "nuke": 1}


def test_request_emails_the_maintainer(client, signed_in, app, settings, capsys):
    post = make_post(app, store.create_pass(app.conn))
    signed_in.post("/moderation-request", data={"item_id": post.id, "kind": "unhide"}, follow_redirects=False)
    out = capsys.readouterr().out
    assert settings.maintainer_email in out
    assert f"post {post.id}" in out
    assert "1 request" in out


def test_request_email_names_no_one(client, signed_in, app, settings):
    from maf.email import moderation_email

    from datetime import UTC, datetime

    sent = datetime(2026, 11, 23, 22, 41, tzinfo=UTC)
    email = moderation_email(settings.maintainer_email, "nuke", "abc123", 3, "https://maforum.net", now=sent)
    assert email.body == ("Deletion requested for post: abc123\nhttps://maforum.net/thread/abc123\n\n"
                          "3 requests so far as of 23/11/26 22:41 UTC\n")
    assert '<a href="https://maforum.net/thread/abc123"' in email.html and "Open the post" not in email.html


# -- CLI -----------------------------------------------------------------


def run_cli(monkeypatch, settings, capsys, *argv, stdin="y\n"):
    import maf.cli as cli_module

    monkeypatch.setattr(cli_module, "_connect", lambda: __import__("maf.db").db.connect(settings.database_path))
    if stdin is not None:
        monkeypatch.setattr("builtins.input", lambda prompt: stdin)
    code = cli(list(argv))
    return code, capsys.readouterr().out


def test_cli_hidden_and_unhide(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    flag_by(app, post.id, 5)
    code, out = run_cli(monkeypatch, settings, capsys, "hidden")
    assert code == 0 and post.id in out
    code, out = run_cli(monkeypatch, settings, capsys, "unhide", post.id)
    assert code == 0
    assert store.get_item(app.conn, post.id).restored == 1


def test_cli_requests(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id, title="Requested post")
    store.add_moderation_request(app.conn, pass_id, post.id, "unhide")
    code, out = run_cli(monkeypatch, settings, capsys, "requests")
    assert code == 0
    assert "Requested post" in out and "unhide" in out


def test_cli_show(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id, title="Shown post")
    flag_by(app, post.id)
    code, out = run_cli(monkeypatch, settings, capsys, "show", post.id)
    assert code == 0
    assert "Shown post" in out and "flags:" in out


def test_cli_unknown_id_exits_non_zero(monkeypatch, settings, app, capsys):
    code, out = run_cli(monkeypatch, settings, capsys, "show", "nope")
    assert code != 0
    assert "No item nope" in out


def test_cli_nuke_deletes_the_thread_after_confirmation(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    store.create_comment(app.conn, pass_id, post, "a comment", None)
    code, _ = run_cli(monkeypatch, settings, capsys, "nuke", post.id, stdin="y\n")
    assert code == 0
    assert store.get_item(app.conn, post.id) is None
    assert app.conn.execute("SELECT COUNT(*) AS n FROM item").fetchone()["n"] == 0


def test_cli_nuke_cancels_by_default(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    code, _ = run_cli(monkeypatch, settings, capsys, "nuke", post.id, stdin="\n")
    assert code == 0
    assert store.get_item(app.conn, post.id) is not None


def test_cli_pin_and_unpin(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    run_cli(monkeypatch, settings, capsys, "pin", post.id)
    assert store.get_item(app.conn, post.id).pinned == 1
    run_cli(monkeypatch, settings, capsys, "unpin", post.id)
    assert store.get_item(app.conn, post.id).pinned == 0


def test_cli_pin_rejects_comments(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    comment = store.create_comment(app.conn, pass_id, post, "c", None)
    code, out = run_cli(monkeypatch, settings, capsys, "pin", comment.id)
    assert code == 1


def test_cli_dismiss(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    store.add_moderation_request(app.conn, pass_id, post.id, "unhide")
    code, _ = run_cli(monkeypatch, settings, capsys, "dismiss", post.id)
    assert code == 0
    assert store.request_counts(app.conn, post.id) == {}


def test_emails_have_html_in_the_site_style_and_a_plain_text_fallback():
    from maf.email import _body, code_email, moderation_email

    code = code_email("student@uni.minerva.edu", "482913")
    assert "482913" in code.html and "482913" in code.body
    assert ">MAF</p>" in code.html and "light only" in code.html
    assert "prefers-color-scheme" not in code.html
    assert "Iowan Old Style" in code.html
    assert set(_body(code)) == {"Text", "Html"}

    request = moderation_email("me@example.com", "unhide", "<b>x</b>", 2, "https://maforum.net")
    assert "&lt;b&gt;x&lt;/b&gt;" in request.html and "<b>x</b>" not in request.html
    assert "2 requests so far" in request.html


def test_clicking_flag_again_takes_it_back(signed_in, app, pass_id):
    post = make_post(app, store.create_pass(app.conn))
    signed_in.post("/flag", data={"item_id": post.id})
    assert store.get_item(app.conn, post.id).flags == 1
    page = signed_in.get(f"/thread/{post.id}").text
    assert 'class="meta-action flagged"' in page and ">Flagged<" in page
    signed_in.post("/flag", data={"item_id": post.id})
    assert store.get_item(app.conn, post.id).flags == 0
    assert ">Flag Post<" in signed_in.get(f"/thread/{post.id}").text


def test_a_post_hidden_by_flags_returns_when_one_is_taken_back(app, pass_id):
    post = make_post(app, pass_id)
    flaggers = [store.create_pass(app.conn) for _ in range(5)]
    for flagger in flaggers:
        store.add_flag(app.conn, flagger, post.id)
    assert store.get_item(app.conn, post.id).hidden == 1
    store.remove_flag(app.conn, flaggers[0], post.id)
    assert store.get_item(app.conn, post.id).hidden == 0


def test_a_comment_with_five_flags_is_replaced_by_a_note_and_its_replies_stay(client, app, pass_id):
    from tests.conftest import sign_in_as

    post = store.create_post(app.conn, pass_id, "Post", "text", None, [])
    flagged = store.create_comment(app.conn, pass_id, post, "rude words here", None)
    store.create_comment(app.conn, store.create_pass(app.conn), flagged, "a reply that stays", None)
    for _ in range(5):
        store.add_flag(app.conn, store.create_pass(app.conn), flagged.id)
    page = sign_in_as(client, app, pass_id).get(f"/thread/{post.id}").text
    assert "rude words here" not in page
    assert "Original reply is in review after 5 flags." in page
    assert "a reply that stays" in page


def test_flagging_a_comment_says_comment(client, app, pass_id):
    from tests.conftest import sign_in_as

    post = store.create_post(app.conn, pass_id, "Post", "text", None, [])
    comment = store.create_comment(app.conn, pass_id, post, "a comment", None)
    viewer = sign_in_as(client, app, store.create_pass(app.conn))
    page = viewer.post("/flag", data={"item_id": comment.id}).text
    assert "5 flags hide a comment." in page


def test_maintainer_gets_one_email_when_flags_hide_a_reply(client, app, pass_id, capsys):
    from tests.conftest import sign_in_as

    post = store.create_post(app.conn, pass_id, "Post", "text", None, [])
    reply = store.create_comment(app.conn, pass_id, post, "rude words here", None)
    flaggers = [store.create_pass(app.conn) for _ in range(5)]
    for flagger in flaggers:
        sign_in_as(client, app, flagger).post("/flag", data={"item_id": reply.id})
    # The last flagger takes it back and flags again: still only one email.
    sign_in_as(client, app, flaggers[-1]).post("/flag", data={"item_id": reply.id})
    sign_in_as(client, app, flaggers[-1]).post("/flag", data={"item_id": reply.id})
    out = capsys.readouterr().out
    assert out.count("[email to maintainer@example.com] MAF review requested for reply") == 1
    assert f"{app.settings.base_url}/thread/{post.id}#{reply.id}" in out
    assert "rude words here" not in out


def test_hidden_reply_email_matches_the_post_layout():
    from datetime import UTC, datetime

    from maf.email import hidden_reply_email

    email = hidden_reply_email("m@example.com", "calm-otter-river", "quiet-river-lantern", 5, "https://maforum.net",
                               now=datetime(2026, 11, 24, 7, 5, tzinfo=UTC))
    assert email.subject == "MAF review requested for reply calm-otter-river"
    assert "Review requested for reply: calm-otter-river" in email.body
    assert "Hidden after 5 flags as of 24/11/26 07:05 UTC" in email.body
    assert "maf show calm-otter-river" in email.html
    assert "https://maforum.net/thread/quiet-river-lantern#calm-otter-river" in email.html


def test_flags_hiding_a_post_send_no_email(client, app, pass_id, capsys):
    from tests.conftest import sign_in_as

    post = store.create_post(app.conn, pass_id, "Post", "text", None, [])
    for _ in range(5):
        sign_in_as(client, app, store.create_pass(app.conn)).post("/flag", data={"item_id": post.id})
    assert "[email to" not in capsys.readouterr().out


# -- remove with a reason ------------------------------------------------


def test_cli_remove_deletes_the_words_and_shows_the_reason(monkeypatch, settings, app, pass_id, signed_in, capsys):
    post = make_post(app, pass_id)
    comment = store.create_comment(app.conn, pass_id, post, "Zorblax wrote this badly", None)
    reply = store.create_comment(app.conn, pass_id, comment, "a reply underneath", None)
    store.toggle_reaction(app.conn, pass_id, comment.id, "👍")
    code, out = run_cli(monkeypatch, settings, capsys, "remove", comment.id, stdin="y\n")
    assert code == 0
    assert "Zorblax" not in out  # the command never prints what was written
    removed = store.get_item(app.conn, comment.id)
    assert removed.text is None and removed.removed_reason == "Removed because it named someone."
    assert store.search(app.conn, "Zorblax") == []
    page = signed_in.get(f"/thread/{post.id}").text
    assert "Removed because it named someone." in page and "Zorblax" not in page
    assert "a reply underneath" in page and store.get_item(app.conn, reply.id) is not None
    assert app.conn.execute("SELECT COUNT(*) AS n FROM reaction WHERE item_id = ?", (comment.id,)).fetchone()["n"] == 0


def test_cli_remove_takes_a_custom_reason_and_cancels_by_default(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    comment = store.create_comment(app.conn, pass_id, post, "words", None)
    run_cli(monkeypatch, settings, capsys, "remove", comment.id, stdin="\n")
    assert store.get_item(app.conn, comment.id).text == "words"
    run_cli(monkeypatch, settings, capsys, "remove", comment.id, "--reason", "Removed: spam.", "--yes")
    assert store.get_item(app.conn, comment.id).removed_reason == "Removed: spam."


def test_cli_remove_refuses_posts(monkeypatch, settings, app, pass_id, capsys):
    post = make_post(app, pass_id)
    code, out = run_cli(monkeypatch, settings, capsys, "remove", post.id, "--yes")
    assert code != 0 and "posts can only be nuked" in out
