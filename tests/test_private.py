"""Private replies: who sees them, what they're excluded from, and how they nest."""

import base64
import json
import os
import sqlite3

from maf import db, store
from maf.sealed import parse_sealed
from tests.conftest import sign_in_as


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def public_key() -> str:
    """Shaped like an uncompressed P-256 point; the server only checks the shape."""
    return b64(b"\x04" + os.urandom(64))


def sealed_json(sender_key: str, recipient_key: str) -> str:
    return json.dumps({"v": 1, "iv": b64(os.urandom(12)), "ct": b64(os.urandom(40)), "from": sender_key, "to": recipient_key})


def register_keys(app, thread_id, *pass_ids):
    keys = [public_key() for _ in pass_ids]
    for pass_id, key in zip(pass_ids, keys):
        store.set_thread_key(app.conn, pass_id, thread_id, key)
    return keys


def make_post(app, pass_id, title="A post", text="text"):
    return store.create_post(app.conn, pass_id, title, text, None, [])


def add_comment(app, pass_id, parent, text="hi", private_to=None):
    return store.create_comment(app.conn, pass_id, parent, text, private_to)


def visible_texts(app, thread_id, viewer):
    return [i.text for i in store.thread_items(app.conn, thread_id, viewer)]


def test_only_the_two_parties_see_a_private_reply(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    stranger = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "just for op", private_to=op)
    assert "just for op" in visible_texts(app, post.id, op)
    assert "just for op" in visible_texts(app, post.id, other)
    assert "just for op" not in visible_texts(app, post.id, stranger)
    assert "just for op" not in visible_texts(app, post.id, None)


def test_descendants_of_a_private_reply_are_hidden_with_it(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    stranger = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "secret", private_to=op)
    reply = add_comment(app, op, private, "reply inside", private_to=other)
    assert "reply inside" in visible_texts(app, post.id, op)
    assert "reply inside" not in visible_texts(app, post.id, stranger)


def test_replies_to_a_private_item_are_forced_private(app, client):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    private = add_comment(app, other, post, "secret", private_to=op)
    op_key, other_key = register_keys(app, post.id, op, other)
    sign_in_as(client, app, op).post(
        "/comment", data={"parent_id": private.id, "sealed": sealed_json(op_key, other_key)}, follow_redirects=False)
    child = app.conn.execute("SELECT private_to, text FROM item WHERE parent_id = ?", (private.id,)).fetchone()
    assert child["private_to"] == other
    assert child["text"] is None


def test_private_items_are_excluded_from_counts_search_and_tags(app):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    add_comment(app, other, post, "uniqueword", private_to=op)
    assert store.comment_count(app.conn, post.id) == 0
    assert store.search(app.conn, "uniqueword") == []


def test_cannot_reply_privately_to_yourself(app, signed_in, pass_id):
    post = make_post(app, pass_id)
    signed_in.post("/comment", data={"parent_id": post.id, "text": "note to self", "private": "on"}, follow_redirects=False)
    row = app.conn.execute("SELECT private_to FROM item WHERE parent_id = ?", (post.id,)).fetchone()
    assert row["private_to"] is None


def test_private_reply_is_stored_only_sealed(app, client):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    (op_key,) = register_keys(app, post.id, op)
    other_key = public_key()
    sealed = sealed_json(other_key, op_key)
    sign_in_as(client, app, other).post(
        "/comment", data={"parent_id": post.id, "private": "on", "sealed": sealed, "text": "plain words"},
        follow_redirects=False)
    row = app.conn.execute("SELECT text, sealed, private_to FROM item WHERE parent_id = ?", (post.id,)).fetchone()
    assert row["text"] is None
    assert json.loads(row["sealed"]) == json.loads(sealed)
    assert row["private_to"] == op
    # The sender's key is saved from their first private reply, so the OP can answer privately.
    assert store.thread_keys(app.conn, post.id)[other] == other_key


def test_private_reply_without_a_sealed_copy_is_not_saved(app, client):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    register_keys(app, post.id, op)
    response = sign_in_as(client, app, other).post(
        "/comment", data={"parent_id": post.id, "private": "on", "text": "plain words"}, follow_redirects=False)
    assert "need+JavaScript" in response.headers["location"]
    assert app.conn.execute("SELECT COUNT(*) FROM item WHERE parent_id = ?", (post.id,)).fetchone()[0] == 0


def test_private_reply_must_be_sealed_to_the_recipients_key(app, client):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    post = make_post(app, op)
    register_keys(app, post.id, op)
    response = sign_in_as(client, app, other).post(
        "/comment", data={"parent_id": post.id, "private": "on", "sealed": sealed_json(public_key(), public_key())},
        follow_redirects=False)
    assert "Reload+the+page" in response.headers["location"]
    assert app.conn.execute("SELECT COUNT(*) FROM item WHERE parent_id = ?", (post.id,)).fetchone()[0] == 0


def test_thread_page_shows_the_sealed_copy_only_to_the_two_people(app, client):
    op = store.create_pass(app.conn)
    other = store.create_pass(app.conn)
    stranger = store.create_pass(app.conn)
    post = make_post(app, op)
    op_key, other_key = register_keys(app, post.id, op, other)
    sealed = sealed_json(other_key, op_key)
    store.create_comment(app.conn, other, post, None, op, sealed=sealed)
    marker = json.loads(sealed)["ct"]
    assert marker in sign_in_as(client, app, op).get(f"/thread/{post.id}").text
    assert marker in sign_in_as(client, app, other).get(f"/thread/{post.id}").text
    assert marker not in sign_in_as(client, app, stranger).get(f"/thread/{post.id}").text


def test_thread_keys_are_only_saved_for_people_who_wrote_in_the_thread(app, client):
    op = store.create_pass(app.conn)
    reader = store.create_pass(app.conn)
    post = make_post(app, op)
    key = public_key()
    form = {"thread_id": post.id, "public_key": key}
    assert client.post("/thread-key", data=form, follow_redirects=False).status_code in (303, 401)  # the sign-in gate answers first
    assert sign_in_as(client, app, reader).post("/thread-key", data=form).status_code == 403
    assert sign_in_as(client, app, op).post("/thread-key", data={**form, "public_key": "short"}).status_code == 400
    assert sign_in_as(client, app, op).post("/thread-key", data=form).status_code == 204
    assert store.thread_keys(app.conn, post.id) == {op: key}


def test_thread_page_asks_only_participants_for_a_key(app, client):
    op = store.create_pass(app.conn)
    reader = store.create_pass(app.conn)
    post = make_post(app, op)
    assert 'data-my-key=""' in sign_in_as(client, app, op).get(f"/thread/{post.id}").text
    assert "data-my-key" not in sign_in_as(client, app, reader).get(f"/thread/{post.id}").text


def test_deleting_a_thread_removes_its_keys(app):
    op = store.create_pass(app.conn)
    post = make_post(app, op)
    register_keys(app, post.id, op)
    store.delete_item(app.conn, post.id)
    assert store.thread_keys(app.conn, post.id) == {}


def test_parse_sealed_rejects_anything_that_is_not_a_sealed_reply():
    good = sealed_json(public_key(), public_key())
    assert parse_sealed(good) is not None
    assert parse_sealed("plain words") is None
    assert parse_sealed("") is None
    assert parse_sealed(json.dumps({**json.loads(good), "text": "plain"})) is None
    assert parse_sealed(json.dumps({**json.loads(good), "iv": b64(b"short")})) is None
    assert parse_sealed(json.dumps({**json.loads(good), "to": b64(os.urandom(65))[:-2]})) is None
    assert parse_sealed(json.dumps({**json.loads(good), "v": 2})) is None


def test_existing_database_gains_sealed_replies_without_losing_data(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(db.SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO item (id, thread_id, pass_id, title, created_at) VALUES ('a', 'a', 'p', 'Old', '2026-11-24')")
    conn.commit()
    conn.close()
    conn = db.connect(path)
    db.migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT title, sealed FROM item").fetchone()[:] == ("Old", None)
    assert conn.execute("SELECT COUNT(*) FROM thread_key").fetchone()[0] == 0
