"""Dates, end to end on the server: sending a profile, matching, Unmatch, Hide, deleting, and what's refused."""

from maf import profiles, store
from tests.conftest import sign_in_as
from tests.test_private import register_keys, sealed_json

ANSWERS = {"region": "Europe", "gender": "Woman", "height": "Over 5′9″ (175 cm)", "city": "Tokyo", "looking_for": "Friend"}


def _profile(app, pass_id):
    return store.create_post(app.conn, pass_id, profiles.title_of(ANSWERS), profiles.text_of(ANSWERS), None, [], board="dates")


def _people(app, client):
    """An owner with a profile and a sender with one, both with keys on the owner's profile."""
    owner, sender = store.create_pass(app.conn), store.create_pass(app.conn)
    profile = _profile(app, owner)
    _profile(app, sender)
    owner_key, sender_key = register_keys(app, profile.id, owner, sender)
    return owner, sender, profile, owner_key, sender_key


def _send(client, profile, sender_key, owner_key, parent=None):
    return client.post("/comment", data={"parent_id": (parent or profile).id, "thread_id": profile.id, "private": "on",
                                         "sealed": sealed_json(sender_key, owner_key)}, follow_redirects=False)


def _top_reply(app, profile, pass_id):
    return next(i for i in store.thread_items(app.conn, profile.id, pass_id) if i.parent_id == profile.id and i.pass_id == pass_id)


def test_a_profile_is_sent_once_and_only_its_owner_and_sender_see_it(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    assert "notice" not in _send(client, profile, sender_key, owner_key).headers["location"]
    assert "already+sent" in _send(client, profile, sender_key, owner_key).headers["location"]
    stranger = store.create_pass(app.conn)
    assert [i.id for i in store.thread_items(app.conn, profile.id, stranger)] == [profile.id]
    assert len(store.thread_items(app.conn, profile.id, owner)) == 2


def test_no_profile_no_sending_and_no_public_replies_or_reactions(client, app):
    owner = store.create_pass(app.conn)
    profile = _profile(app, owner)
    lurker = store.create_pass(app.conn)
    _, lurker_key = register_keys(app, profile.id, owner, lurker)
    owner_key = store.thread_keys(app.conn, profile.id)[owner]
    sign_in_as(client, app, lurker)
    assert "need+a+profile" in _send(client, profile, lurker_key, owner_key).headers["location"]
    public = client.post("/comment", data={"parent_id": profile.id, "thread_id": profile.id, "text": "hey"}, follow_redirects=False)
    assert "are+private" in public.headers["location"]
    client.post("/react", data={"item_id": profile.id, "thread_id": profile.id, "emoji": "👍"})
    assert len(store.thread_items(app.conn, profile.id, owner)) == 1
    assert not app.conn.execute("SELECT COUNT(*) FROM reaction").fetchone()[0]


def test_the_sender_waits_for_the_owner_to_write_first(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    _send(client, profile, sender_key, owner_key)
    reply = _top_reply(app, profile, sender)
    assert "once+they+match" in _send(client, profile, sender_key, owner_key, parent=reply).headers["location"]
    sign_in_as(client, app, owner)
    assert "notice" not in _send(client, profile, owner_key, sender_key, parent=reply).headers["location"]
    sign_in_as(client, app, sender)
    assert "notice" not in _send(client, profile, sender_key, owner_key, parent=reply).headers["location"]


def test_unmatch_erases_the_messages_for_both_and_ends_the_match(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    _send(client, profile, sender_key, owner_key)
    reply = _top_reply(app, profile, sender)
    store.create_comment(app.conn, owner, reply, None, sender, sealed=sealed_json(owner_key, sender_key))
    response = client.post("/dates/unmatch", data={"reply_id": reply.id}, follow_redirects=False)
    assert "Unmatched" in response.headers["location"]
    items = store.thread_items(app.conn, profile.id, owner)
    assert [i.id for i in items] == [profile.id, reply.id] and items[1].removed_reason == store.MATCH_ENDED
    assert items[1].sealed is None
    assert "This+match+ended" in _send(client, profile, sender_key, owner_key, parent=reply).headers["location"]
    page = client.get(f"/dates/thread/{profile.id}").text
    assert "disabled>Match ended<" in page
    sign_in_as(client, app, owner)
    assert "This match ended." in client.get(f"/dates/thread/{profile.id}").text


def test_only_the_two_can_unmatch_and_only_the_owner_can_hide(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    _send(client, profile, sender_key, owner_key)
    reply = _top_reply(app, profile, sender)
    client.post("/dates/hide", data={"reply_id": reply.id})
    sign_in_as(client, app, store.create_pass(app.conn))
    client.post("/dates/unmatch", data={"reply_id": reply.id})
    assert store.get_item(app.conn, reply.id).removed_reason is None


def test_hide_leaves_the_owner_nothing_and_the_sender_replied(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    _send(client, profile, sender_key, owner_key)
    reply = _top_reply(app, profile, sender)
    sign_in_as(client, app, owner)
    client.post("/dates/hide", data={"reply_id": reply.id})
    page = client.get(f"/dates/thread/{profile.id}").text
    assert f'id="{reply.id}"' not in page and "replied with" not in page
    sign_in_as(client, app, sender)
    page = client.get(f"/dates/thread/{profile.id}").text
    assert "disabled>Replied<" in page and f'id="{reply.id}"' not in page
    assert "already+sent" in _send(client, profile, sender_key, owner_key).headers["location"]


def test_deleting_your_profile_takes_back_the_ones_you_sent(client, app):
    owner, sender, profile, owner_key, sender_key = _people(app, client)
    sign_in_as(client, app, sender)
    _send(client, profile, sender_key, owner_key)
    reply = _top_reply(app, profile, sender)
    client.post("/dates/delete")
    assert store.get_item(app.conn, reply.id).removed_reason == store.HIDDEN_BY_OWNER
    sign_in_as(client, app, owner)
    assert f'id="{reply.id}"' not in client.get(f"/dates/thread/{profile.id}").text


def test_reply_with_profile_waits_for_the_owners_device_key(client, app):
    owner, sender = store.create_pass(app.conn), store.create_pass(app.conn)
    profile = _profile(app, owner)
    _profile(app, sender)
    sign_in_as(client, app, sender)
    assert "once they open theirs on their device" in client.get(f"/dates/thread/{profile.id}").text


def test_the_send_form_comes_before_the_script_that_encrypts_it(client, app):
    owner, sender, profile, *_ = _people(app, client)
    sign_in_as(client, app, sender)
    page = client.get(f"/dates/thread/{profile.id}").text
    assert page.index('id="send-dialog"') < page.index("private.js")


def test_a_profile_is_flagged_as_a_profile(client, app):
    owner, sender, profile, *_ = _people(app, client)
    sign_in_as(client, app, sender)
    assert "Flag Profile" in client.get(f"/dates/thread/{profile.id}").text
