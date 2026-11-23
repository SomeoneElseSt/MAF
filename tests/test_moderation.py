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
    page = client.get(f"/item/{post.id}")
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
    assert f"post #{post.id}" in out
    assert "1 request" in out


def test_request_email_names_no_one(client, signed_in, app, settings):
    from maf.email import moderation_email

    email = moderation_email(settings.maintainer_email, "nuke", "abc123", 3, "https://maforum.net")
    assert email.body == "Deletion requested for post #abc123 (3 requests so far).\nhttps://maforum.net/item/abc123\n"


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
    assert "No item #nope" in out


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
    page = signed_in.get(f"/item/{post.id}").text
    assert 'class="meta-action flagged"' in page and ">Flagged<" in page
    signed_in.post("/flag", data={"item_id": post.id})
    assert store.get_item(app.conn, post.id).flags == 0
    assert ">Flag Post<" in signed_in.get(f"/item/{post.id}").text


def test_a_post_hidden_by_flags_returns_when_one_is_taken_back(app, pass_id):
    post = make_post(app, pass_id)
    flaggers = [store.create_pass(app.conn) for _ in range(5)]
    for flagger in flaggers:
        store.add_flag(app.conn, flagger, post.id)
    assert store.get_item(app.conn, post.id).hidden == 1
    store.remove_flag(app.conn, flaggers[0], post.id)
    assert store.get_item(app.conn, post.id).hidden == 0
