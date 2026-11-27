"""Writing: posts, comments, flags, moderation requests and API tokens."""

import json
import secrets
from urllib.parse import quote_plus, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import live, profiles, push, store
from .email import hidden_reply_email, moderation_email
from .housetags import submit_placeholder
from .sealed import parse_sealed, valid_public_key
from .util import sha256_hex
from .web import form_values, gone, page_of, redirect, render, render_dates, to_thread

POSTS_PER_MINUTE = 6
# The thread page shows the name-check warning by the box it belongs to, so the reply or edit stays
# open with its words (drafts.js refills them). This line just says what happened.
NAMES_NOTICE = "That+wasn't+sent:+it+looks+like+it+names+someone."
COMMENTS_PER_MINUTE = 12
NSFW_YES, NSFW_NO = "Yes", "No"  # the answers to "Is NSFW?" on the submit form
TOKEN_BYTES = 32
MAX_TOKENS_PER_PASS = 5  # the Create token button greys out at this many


def _login(page) -> Response:
    return redirect("/sign-in")


def _allowed(page, key: str, limit: int) -> bool:
    return page.memory.allow(f"{key}:{page.pass_id}", limit)


async def submit_page(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    tags: list[str] = []
    return render(page, "submit.html", placeholder=submit_placeholder(tags),
                  values={}, errors={})


async def submit_post(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    values = await form_values(request, "title", "url", "text", "tags", "nsfw", "confirm_names")
    tags, too_many = store.normalise_tags(values["tags"])
    errors = _validate_post(values, too_many)
    if errors:
        return _form_error(page, values, tags, errors)
    if values["confirm_names"] != "1" and await run_in_threadpool(page.app.name_filter.finds_name, values["title"], values["text"]):
        return _name_warning(page, values, tags)
    if not _allowed(page, "post", POSTS_PER_MINUTE):
        return _form_error(page, values, tags, {"form": "You're posting fast. Wait a minute and try again."})
    post = store.create_post(
        page.conn, page.pass_id, values["title"], values["text"] or None, values["url"] or None, tags,
        nsfw=values["nsfw"] == NSFW_YES,
    )
    page.app.live.publish(live.HOME)
    return to_thread(page, post.id)


async def save_profile(request: Request) -> Response:
    """Posts your Dates profile, or saves changes to it: one per pass, written only from its answers (profiles.py)."""
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    values = await form_values(request, *profiles.CHOICES, "comment", "can_encrypt")
    profile = store.own_profile(page.conn, page.pass_id)
    errors = await _profile_errors(page, values)
    if profile is None and values["can_encrypt"] != "1":  # replies are encrypted for this device (dates-form.js)
        errors = {**errors, "form": "Your browser doesn't seem to support JavaScript. Turn it on, or use another browser."}
    if errors:
        return render_dates(page, "dates-submit.html", status_code=400, profile=profile, choices=profiles.CHOICES,
                            title="Edit your profile" if profile else "Make your profile", values=values, errors=errors)
    title, text = profiles.title_of(values), profiles.text_of(values)
    if profile is not None:
        store.edit_item(page.conn, profile.id, text, title=title)
        return to_thread(page, profile.id)
    profile = store.create_post(page.conn, page.pass_id, title, text, None, [], board="dates")
    page.app.live.publish(live.HOME)
    return to_thread(page, profile.id)


async def _profile_errors(page, values: dict[str, str]) -> dict[str, str]:
    errors = profiles.missing(values)
    if len(values["comment"]) > store.BODY_MAX:
        errors["comment"] = "That's too long. Try trimming it."
    if errors:
        return errors
    if values["comment"] and await run_in_threadpool(page.app.name_filter.finds_name, values["comment"]):
        return {"comment": "It looks like this names someone. Take the name out and save again."}
    if not _allowed(page, "post", POSTS_PER_MINUTE):
        return {"form": "You're posting fast. Wait a minute and try again."}
    return {}


async def delete_profile(request: Request) -> Response:
    """Deletes your profile with everything under it: the profiles people sent you and your conversations."""
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    profile = store.own_profile(page.conn, page.pass_id)
    if profile is not None:
        store.delete_own_post(page.conn, profile.id)
        store.close_sent_profiles(page.conn, page.pass_id)
        page.app.live.publish(live.HOME)
    return redirect("/dates")


def _validate_post(values: dict[str, str], too_many: bool) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not values["title"]:
        errors["title"] = "Add a title."
    elif len(values["title"]) > store.TITLE_MAX:
        errors["title"] = f"Keep the title under {store.TITLE_MAX} characters."
    if values["url"] and not _valid_url(values["url"]):
        errors["url"] = "That link doesn't look like a web address."
    if len(values["text"]) > store.BODY_MAX:
        errors["text"] = "That's too long. Try trimming it."
    if too_many:
        errors["tags"] = "Use at most 3 hashtags."
    if values["nsfw"] not in (NSFW_YES, NSFW_NO):
        errors["nsfw"] = "Choose Yes or No."
    return errors


def _valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _form_error(page, values, tags, errors) -> Response:
    return render(page, "submit.html", status_code=400,
                  placeholder=submit_placeholder(tags), values=values, errors=errors)


def _name_warning(page, values, tags) -> Response:
    return render(page, "submit-warning.html", status_code=400,
                  placeholder=submit_placeholder(tags), values=values)


async def comment(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "parent_id", "thread_id", "text", "private", "confirm_names", "sealed")
    parent = store.get_item(page.conn, values["parent_id"])
    if page.pass_id is None or parent is None:
        return gone(page, values["thread_id"])
    private_to = _private_recipient(page, parent, values["private"] == "on")
    refusal = _profile_refusal(page, parent, private_to)
    if refusal:
        return to_thread(page, parent.thread_id, f"?notice={quote_plus(refusal)}")
    if private_to is not None:
        return _private_comment(page, parent, private_to, values["sealed"])
    if not values["text"]:
        return to_thread(page, parent.thread_id, "?notice=Write+something+first.")
    if values["confirm_names"] != "1" and await run_in_threadpool(page.app.name_filter.finds_name, values["text"]):
        # The thread page shows the warning and "Post anyway" inside this box (the name check can be wrong).
        return to_thread(page, parent.thread_id, f"?notice={NAMES_NOTICE}&names={_names_box(parent)}&text={quote_plus(values['text'])}")
    if not _allowed(page, "comment", COMMENTS_PER_MINUTE):
        return to_thread(page, parent.thread_id, "?notice=You're+replying+fast.+Wait+a+minute.")
    reply = store.create_comment(page.conn, page.pass_id, parent, values["text"], None)
    page.app.live.publish(parent.thread_id)
    page.app.live.publish(live.HOME)  # front pages refresh their New section and counts
    _ring(page, parent.pass_id)
    _ring_subscribers(page, parent.thread_id)
    push.alert_reply(page, reply)
    return to_thread(page, parent.thread_id, f"#{reply.id}")  # land on the new reply, not the top


def _names_box(parent: store.Item) -> str:
    """The reply box a refused reply came from: the top one, or the one under the reply it answers."""
    return "comment-form" if parent.id == parent.thread_id else f"reply-{parent.id}"


def _private_comment(page, parent: store.Item, private_to: str, raw_sealed: str) -> Response:
    """Stores a private reply only in its encrypted form; any plain text sent along is dropped.

    The name filter can't run here: the server never sees the words.
    """
    thread_id = parent.thread_id
    sealed = parse_sealed(raw_sealed)
    if sealed is None:
        return to_thread(page, thread_id, "?notice=Private+replies+need+JavaScript.+Turn+it+on+and+try+again.")
    keys = store.thread_keys(page.conn, parent.thread_id)
    own_key = keys.get(page.pass_id)
    if keys.get(private_to) != sealed["to"] or own_key not in (None, sealed["from"]):
        return to_thread(page, thread_id, "?notice=Couldn't+send+that+privately.+Reload+the+page+and+try+again.")
    if not _allowed(page, "comment", COMMENTS_PER_MINUTE):
        return to_thread(page, thread_id, "?notice=You're+replying+fast.+Wait+a+minute.")
    if own_key is None:
        store.set_thread_key(page.conn, page.pass_id, parent.thread_id, sealed["from"])
    reply = store.create_comment(page.conn, page.pass_id, parent, None, private_to, sealed=json.dumps(sealed))
    page.app.live.publish(parent.thread_id)
    if parent.pass_id == private_to:
        _ring(page, private_to)
    push.alert_reply(page, reply)
    return to_thread(page, thread_id, f"#{reply.id}")


def _profile_refusal(page, parent: store.Item, private_to: str | None) -> str | None:
    """On a profile, replies are only private: your profile sent to its owner once, then messages in a match."""
    post = parent if parent.is_post else store.get_item(page.conn, parent.thread_id)
    if not store.is_profile(post):
        return None
    if private_to is None:
        return "Replies on a profile are private."
    if not parent.is_post:
        top = parent if parent.parent_id == post.id else _top_reply(page, parent, post)
        if top.removed_reason:
            return "This match ended."
        # The owner's first message is the match; until then the sender can't write.
        waiting = page.pass_id == top.pass_id and not store.reply_count(page.conn, top.id)
        return "You can write once they match with you." if waiting else None
    if not store.has_profile(page.conn, page.pass_id):
        return "You need a profile to reply."
    already = page.conn.execute("SELECT 1 FROM item WHERE parent_id = ? AND pass_id = ?", (post.id, page.pass_id)).fetchone()
    return "You've already sent your profile." if already else None


def _top_reply(page, item: store.Item, post: store.Item) -> store.Item:
    while item.parent_id != post.id:
        item = store.get_item(page.conn, item.parent_id)
    return item


async def unmatch(request: Request) -> Response:
    """Either of the two ends a match: the messages are erased for both, and "This match ended." stays."""
    page = page_of(request)
    reply, post = await _profile_reply_of(request, page)
    if reply is None or page.pass_id not in (post.pass_id, reply.pass_id):
        return gone(page, post.id if post else "")
    store.close_profile_reply(page.conn, reply.id, store.MATCH_ENDED)
    page.app.live.publish(post.id)
    return to_thread(page, post.id, "?notice=Unmatched.+Your+messages+are+erased+for+both+of+you.")


async def hide_profile_reply(request: Request) -> Response:
    """The profile's owner hides a profile someone sent: it goes, and that person can't send it again."""
    page = page_of(request)
    reply, post = await _profile_reply_of(request, page)
    if reply is None or page.pass_id != post.pass_id:
        return gone(page, post.id if post else "")
    store.close_profile_reply(page.conn, reply.id, store.HIDDEN_BY_OWNER)
    page.app.live.publish(post.id)
    return to_thread(page, post.id)


async def _profile_reply_of(request: Request, page) -> tuple[store.Item | None, store.Item | None]:
    """The open profile reply a form names, with its profile; (None, profile or None) if it isn't one."""
    values = await form_values(request, "reply_id")
    reply = store.get_item(page.conn, values["reply_id"])
    post = store.get_item(page.conn, reply.thread_id) if reply else None
    if page.pass_id is None or post is None or not store.is_profile(post):
        return None, post
    if reply.parent_id != post.id or reply.removed_reason:
        return None, post
    return reply, post


def _ring(page, owner: str) -> None:
    """Tells the owner's bell something new arrived (nothing is stored; their page re-checks)."""
    if owner != page.pass_id:
        page.app.live.publish(live.bell(owner))


def _ring_subscribers(page, thread_id: str) -> None:
    """Same for everyone following the post, so their Feed picks up the activity."""
    for pass_id in store.subscribers(page.conn, thread_id):
        _ring(page, pass_id)


def _own_item(page, item: store.Item | None) -> bool:
    return item is not None and page.pass_id is not None and item.pass_id == page.pass_id


def _own_reply(page, item: store.Item | None) -> bool:
    return _own_item(page, item) and not item.is_post


async def edit(request: Request) -> Response:
    """Changes your own post or reply to the words you send. The thread notes it was edited."""
    page = page_of(request)
    values = await form_values(request, "item_id", "thread_id", "text", "sealed", "confirm_names")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return gone(page, values["thread_id"])
    thread_id = item.thread_id
    if not _own_item(page, item) or item.removed_reason or item.unlisted:
        what = "posts" if item.is_post else "replies"
        return to_thread(page, thread_id, f"?notice=You+can+only+edit+your+own+{what}.")
    if not _allowed(page, "comment", COMMENTS_PER_MINUTE):
        return to_thread(page, thread_id, "?notice=You're+editing+fast.+Wait+a+minute.")
    if item.private_to:
        return _private_edit(page, item, values["sealed"])
    if not values["text"]:
        return to_thread(page, thread_id, "?notice=Write+something+first.")
    if len(values["text"]) > store.BODY_MAX:
        return to_thread(page, thread_id, "?notice=That's+too+long.+Try+trimming+it.")
    if values["confirm_names"] != "1" and await run_in_threadpool(page.app.name_filter.finds_name, values["text"]):
        # Same as a refused reply: the warning shows in the edit box, with the words.
        return to_thread(page, thread_id, f"?notice={NAMES_NOTICE}&names=edit-{item.id}&text={quote_plus(values['text'])}")
    store.edit_item(page.conn, item.id, values["text"])
    return to_thread(page, thread_id, f"#{item.id}")


def _private_edit(page, item: store.Item, raw_sealed: str) -> Response:
    """A private reply's edits are encrypted to the same two people, like the reply itself."""
    thread_id = item.thread_id
    sealed = parse_sealed(raw_sealed)
    if sealed is None:
        return to_thread(page, thread_id, "?notice=Private+replies+need+JavaScript.+Turn+it+on+and+try+again.")
    keys = store.thread_keys(page.conn, item.thread_id)
    if keys.get(page.pass_id) != sealed["from"] or keys.get(item.private_to) != sealed["to"]:
        return to_thread(page, thread_id, "?notice=Couldn't+save+that+privately.+Reload+the+page+and+try+again.")
    store.edit_item(page.conn, item.id, None, sealed=json.dumps(sealed))
    return to_thread(page, thread_id, f"#{item.id}")


async def subscribe(request: Request) -> Response:
    """Follow a whole post: its activity then comes to your Feed. Clicking again stops it."""
    page = page_of(request)
    values = await form_values(request, "thread_id", "back")
    post = store.get_item(page.conn, values["thread_id"])
    if page.pass_id is None or post is None or not post.is_post:
        return gone(page, values["thread_id"])
    back = "#" + values["back"] if values["back"] else ""
    if post.unlisted or post.removed_reason:
        return to_thread(page, post.id, back)
    following = store.is_subscribed(page.conn, page.pass_id, post.id)
    store.set_subscribed(page.conn, page.pass_id, post.id, not following)
    return to_thread(page, post.id, back)


async def hide_post(request: Request) -> Response:
    """Hide Post, for its author: off every list and search, the link still works. Sent again, it unhides."""
    page = page_of(request)
    values = await form_values(request, "thread_id")
    post = store.get_item(page.conn, values["thread_id"])
    if page.pass_id is None or post is None or not post.is_post:
        return gone(page, values["thread_id"])
    if not _own_item(page, post) or store.is_profile(post):
        return to_thread(page, post.id, "?notice=You+can+only+hide+your+own+posts.")
    store.set_author_hidden(page.conn, post.id, not post.author_hidden)
    return to_thread(page, post.id, "")


async def delete_reply(request: Request) -> Response:
    """Deletes your own reply for good; if others replied to it, "Deleted by its author." stays in its place."""
    page = page_of(request)
    values = await form_values(request, "item_id", "thread_id")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return gone(page, values["thread_id"])
    if not _own_reply(page, item):
        return to_thread(page, item.thread_id, "?notice=You+can+only+delete+your+own+replies.")
    store.delete_own_comment(page.conn, item.id)
    # Stay where it was: on its "Deleted by its author." note, else on the reply it answered.
    if store.get_item(page.conn, item.id) is not None:
        return to_thread(page, item.thread_id, f"#{item.id}")
    anchor = f"#{item.parent_id}" if item.parent_id != item.thread_id else ""
    return to_thread(page, item.thread_id, anchor)


async def thread_key(request: Request) -> Response:
    """Saves the viewer's public key for a thread they've written in, so others can reply privately."""
    page = page_of(request)
    values = await form_values(request, "thread_id", "public_key")
    if page.pass_id is None:
        return Response(status_code=401)
    if not valid_public_key(values["public_key"]):
        return Response(status_code=400)
    # Only people who already wrote in the thread, so keys never record which threads someone reads.
    if not store.is_participant(page.conn, page.pass_id, values["thread_id"]):
        return Response(status_code=403)
    store.set_thread_key(page.conn, page.pass_id, values["thread_id"], values["public_key"])
    return Response(status_code=204)


def _private_recipient(page, parent: store.Item, wants_private: bool) -> str | None:
    """The recipient for a private reply, or None for a public one.

    Replies inside a private exchange are forced private to the other party.
    """
    if parent.private_to:
        other = parent.private_to if parent.pass_id == page.pass_id else parent.pass_id
        return None if other == page.pass_id else other
    if not wants_private:
        return None
    recipient = parent.pass_id
    return None if recipient == page.pass_id else recipient


async def flag(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id", "thread_id")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None:
        return gone(page, values["thread_id"])
    # Clicking again takes the flag back.
    if item.private_to is None and not store.remove_flag(page.conn, page.pass_id, item.id):
        store.add_flag(page.conn, page.pass_id, item.id)
        _alert_if_reply_hidden(page, item.id)
    return to_thread(page, item.thread_id, f"#{item.id}")


def _alert_if_reply_hidden(page, item_id: str) -> None:
    """Emails the maintainer when flags hide a reply. Hidden posts email when someone asks for a review."""
    item = store.get_item(page.conn, item_id)
    if item is None or item.is_post or not item.unlisted or not page.memory.take_hide_alert(item.id):
        return
    page.app.emailer.send_soon(hidden_reply_email(page.settings.maintainer_email, item.id, item.thread_id, item.flags,
                                             page.settings.base_url, site=page.settings.site_name))


async def moderation_request(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "item_id", "thread_id", "kind")
    item = store.get_item(page.conn, values["item_id"])
    if page.pass_id is None or item is None or values["kind"] not in {"unhide", "nuke"}:
        return gone(page, values["thread_id"])
    if store.add_moderation_request(page.conn, page.pass_id, item.id, values["kind"]):
        count = sum(store.request_counts(page.conn, item.id).values())
        page.app.emailer.send_soon(
            moderation_email(page.settings.maintainer_email, values["kind"], item.id, count, page.settings.base_url,
                             site=page.settings.site_name)
        )
    return to_thread(page, item.id, "?notice=Request+sent.+Thank+you.")


async def create_token(request: Request) -> Response:
    page = page_of(request)
    if page.pass_id is None:
        return _login(page)
    if len(store.list_api_tokens(page.conn, page.pass_id)) >= MAX_TOKENS_PER_PASS:
        return redirect("/guide/use-this-data")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    store.create_api_token(page.conn, sha256_hex(token), page.pass_id, token[-4:])
    # Redirect so a reload doesn't create another token; the next page load shows it once (see Memory.take_new_token).
    page.memory.hold_new_token(page.pass_id, token)
    return redirect("/guide/use-this-data")


async def revoke_token(request: Request) -> Response:
    page = page_of(request)
    values = await form_values(request, "token_hash")
    if page.pass_id is not None:
        store.revoke_api_token(page.conn, values["token_hash"], page.pass_id)
    return redirect("/guide/use-this-data?notice=Token+revoked.")


routes = [
    Route("/submit", submit_page),
    Route("/submit", submit_post, methods=["POST"]),
    Route("/dates/submit", save_profile, methods=["POST"]),
    Route("/dates/edit", save_profile, methods=["POST"]),
    Route("/dates/delete", delete_profile, methods=["POST"]),
    Route("/dates/unmatch", unmatch, methods=["POST"]),
    Route("/dates/hide", hide_profile_reply, methods=["POST"]),
    Route("/comment", comment, methods=["POST"]),
    Route("/edit", edit, methods=["POST"]),
    Route("/subscribe", subscribe, methods=["POST"]),
    Route("/delete-reply", delete_reply, methods=["POST"]),
    Route("/hide-post", hide_post, methods=["POST"]),
    Route("/thread-key", thread_key, methods=["POST"]),
    Route("/flag", flag, methods=["POST"]),
    Route("/moderation-request", moderation_request, methods=["POST"]),
    Route("/tokens", create_token, methods=["POST"]),
    Route("/tokens/revoke", revoke_token, methods=["POST"]),
]
