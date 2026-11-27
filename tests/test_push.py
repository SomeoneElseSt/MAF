"""Alerts (web push): who gets one for a new reply and what it says, turning a device on and off, and the files
the browser needs (the service worker and the Home Screen manifest)."""

from maf import store

ENDPOINT = "https://push.example.org/send/abc123"


def _post(app, author, board="main"):
    return store.create_post(app.conn, author, "A post", "Some text", None, [], board=board)


def test_a_reply_alerts_whoever_it_answers_with_the_feeds_wording(app):
    author, replier, third = (store.create_pass(app.conn) for _ in range(3))
    post = _post(app, author)
    comment = store.create_comment(app.conn, replier, post, "first", None)
    assert store.reply_alerts(app.conn, comment) == {author: "New reply to your post"}
    answer = store.create_comment(app.conn, third, comment, "second", None)
    assert store.reply_alerts(app.conn, answer)[replier] == "New reply to your comment"


def test_subscribers_get_activity_and_the_replier_gets_nothing(app):
    author, follower, replier = (store.create_pass(app.conn) for _ in range(3))
    post = _post(app, author)
    store.set_subscribed(app.conn, follower, post.id, True)
    store.set_subscribed(app.conn, replier, post.id, True)
    reply = store.create_comment(app.conn, replier, post, "hello", None)
    alerts = store.reply_alerts(app.conn, reply)
    assert alerts[follower] == "New activity on a post you subscribed to"
    assert alerts[author] == "New reply to your post"
    assert replier not in alerts


def test_a_private_reply_alerts_only_the_person_its_for(app):
    author, follower, replier = (store.create_pass(app.conn) for _ in range(3))
    post = _post(app, author)
    store.set_subscribed(app.conn, follower, post.id, True)
    reply = store.create_comment(app.conn, replier, post, None, author, sealed="{}")
    assert store.reply_alerts(app.conn, reply) == {author: "New reply to your post"}


def test_dates_alerts_say_profile_match_and_message(app):
    owner, sender = store.create_pass(app.conn), store.create_pass(app.conn)
    profile = _post(app, owner, board="dates")
    sent = store.create_comment(app.conn, sender, profile, None, owner, sealed="{}")
    assert store.reply_alerts(app.conn, sent) == {owner: "Someone replied with their profile"}
    match = store.create_comment(app.conn, owner, sent, None, sender, created_at="2026-01-01T10:00:00Z", sealed="{}")
    assert store.reply_alerts(app.conn, match) == {sender: "Someone matched with you"}
    message = store.create_comment(app.conn, owner, sent, None, sender, created_at="2026-01-01T10:05:00Z", sealed="{}")
    assert store.reply_alerts(app.conn, message) == {sender: "New message from your match"}


def test_turning_a_device_on_and_off(signed_in, app, pass_id):
    response = signed_in.post("/push/subscribe", data={"endpoint": ENDPOINT, "p256dh": "key", "auth": "secret"})
    assert response.status_code == 204
    assert store.push_devices(app.conn, pass_id) == [{"endpoint": ENDPOINT, "p256dh": "key", "auth": "secret"}]
    assert signed_in.post("/push/unsubscribe", data={"endpoint": ENDPOINT}).status_code == 204
    assert store.push_devices(app.conn, pass_id) == []


def test_a_device_needs_a_pass_and_a_real_push_address(client, signed_in, app):
    assert signed_in.post("/push/subscribe", data={"endpoint": "http://plain.example", "p256dh": "k", "auth": "a"}).status_code == 400
    signed_in.cookies.clear()
    client.post("/push/subscribe", data={"endpoint": ENDPOINT, "p256dh": "k", "auth": "a"})  # sent to Sign in
    assert app.conn.execute("SELECT COUNT(*) FROM push_device").fetchone()[0] == 0


def test_a_device_signing_in_again_moves_to_the_new_pass(app):
    first, second = store.create_pass(app.conn), store.create_pass(app.conn)
    store.add_push_device(app.conn, first, ENDPOINT, "k", "a")
    store.add_push_device(app.conn, second, ENDPOINT, "k2", "a2")
    assert store.push_devices(app.conn, first) == []
    assert store.push_devices(app.conn, second)[0]["p256dh"] == "k2"


def test_someone_else_cant_turn_off_your_device(client, app):
    owner, other = store.create_pass(app.conn), store.create_pass(app.conn)
    store.add_push_device(app.conn, owner, ENDPOINT, "k", "a")
    from tests.conftest import sign_in_as

    sign_in_as(client, app, other).post("/push/unsubscribe", data={"endpoint": ENDPOINT})
    assert len(store.push_devices(app.conn, owner)) == 1


def test_pages_carry_the_key_and_the_files_are_served(signed_in, client):
    page = signed_in.get("/").text
    assert 'data-push-key="' in page and "alerts.js" in page and 'rel="manifest"' in page
    worker = client.get("/sw.js")
    assert worker.status_code == 200 and "showNotification" in worker.text
    assert client.get("/manifest.webmanifest").json()["display"] == "standalone"


def test_signed_out_pages_get_no_key(client):
    assert "data-push-key" not in client.get("/about").text
