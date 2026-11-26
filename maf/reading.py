"""Reading a thread: /thread/<id> (or /nsfw/… or /dates/…, by its board), its view count and the comment tree."""

import re
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from . import embed, live, markdown, navigation, store
from .housetags import etiquette, is_hot, reply_placeholder
from .util import iso, utc_now
from .web import error_page, page_of, redirect, render


NAMES_FORM = re.compile(r"(comment-form|reply-[a-z]+(?:-[a-z]+)*|edit-[a-z]+(?:-[a-z]+)*)")


def _names_form(value: str) -> str | None:
    return value if NAMES_FORM.fullmatch(value) else None


def item(request: Request) -> Response:
    page = page_of(request)
    item_id = request.path_params["id"]
    root = store.get_item(page.conn, item_id)
    if root is None:
        return error_page(page, 404, "That post doesn't exist.")
    if root.private_to and page.pass_id not in (root.pass_id, root.private_to):
        return error_page(page, 404, "That post doesn't exist.")
    thread_id = root.thread_id
    # Each post has one address, under its board (navigation.thread_url); old or other ones redirect there.
    thread_post = root if root.parent_id is None else store.get_item(page.conn, thread_id)
    address = navigation.thread_url(thread_post, item_id)
    if request.url.path != address:
        query = f"?{request.url.query}" if request.url.query else ""
        return redirect(address + query, status_code=302)
    if page.pass_id and page.memory.count_view(page.pass_id, thread_id):
        store.increment_views(page.conn, thread_id)
        root = store.get_item(page.conn, item_id)

    items = store.thread_items(page.conn, thread_id, page.pass_id)
    post = next((i for i in items if i.id == thread_id), root)
    tree = store.build_tree(items, thread_id)
    host = urlsplit(page.settings.base_url).netloc
    embeds = {i.id: embed.embeds_in(page.conn, i.text, page.app.labeler, thread_id, host) for i in items}
    op_pass = post.pass_id
    labels = {i.pass_id for i in items}
    label_of = {pid: page.labeler_label(thread_id, pid) for pid in labels}
    tags = post.tags
    keys = store.thread_keys(page.conn, thread_id)
    participant = bool(page.pass_id) and store.is_participant(page.conn, page.pass_id, thread_id)
    context = {
        "thread_keys": keys,
        "my_key": keys.get(page.pass_id, "") if participant else None,
        "title": markdown.plain(post.title),
        "post": post,
        "board": post.board,  # a Dates post's thread takes the Dates colour
        "post_nsfw": bool(post.nsfw),
        "post_board": navigation.post_board_of(post),  # where the header's links lead (navigation.py)
        # On Dates you answer a profile with your own, so the thread needs to know whether you have one.
        "has_profile": post.board == "dates" and store.has_profile(page.conn, page.pass_id),  # and an NSFW post's the NSFW one, whichever way the switch is
        "comment_count": store.comment_counts(page.conn, [thread_id]).get(thread_id, 0),
        "now": iso(utc_now()),
        "post_mine": bool(page.pass_id) and post.pass_id == page.pass_id,
        "subscribed": store.is_subscribed(page.conn, page.pass_id, post.id),
        "tree": tree,
        "label_of": label_of,
        "op_pass": op_pass,
        "my_label": page.labeler_label(thread_id, page.pass_id) if page.pass_id else None,
        "tags_list": tags,
        "hot": is_hot(tags),
        "etiquette_banner": etiquette(tags),
        "reply_placeholder": reply_placeholder(tags) if tags else "",
        "reactions": _reactions(page, items),
        "embeds": embeds,
        "flags": _flags(page, items),
        "flags_to_hide": store.FLAGS_TO_HIDE,
        "requests": store.request_counts(page.conn, post.id),
        "notice": request.query_params.get("notice"),
        # After the name check refused a reply or edit: which box the warning shows in, and the words it
        # keeps, so "Post anyway" sends exactly them.
        "names_form": _names_form(request.query_params.get("names", "")),
        "names_text": request.query_params.get("text") or "",
        "body_class": "hottakes-thread" if is_hot(tags) else "",
    }
    return render(page, "item.html", **context)


def _reactions(page, items: list[store.Item]) -> dict[str, dict]:
    summary = {}
    for item in items:
        counts, mine = store.reaction_summary(page.conn, item.id, page.pass_id)
        latest = store.latest_reactions(page.conn, item.id, page.pass_id)
        summary[item.id] = {"counts": counts, "mine": mine, "latest": latest}
    return summary


def _flags(page, items: list[store.Item]) -> dict[str, bool]:
    if not page.pass_id:
        return {}
    return {i.id: store.has_flagged(page.conn, page.pass_id, i.id) for i in items}


# Timestamps as stored (util.iso), so they compare as text.
MOMENT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def new_activity(request: Request) -> Response:
    """Rows for the front page's New section that aren't on the page: older posts with new comments.
    The browser sends only when it started counting (no record of what was opened leaves it)."""
    page = page_of(request)
    since = request.query_params.get("since", "")
    if not page.pass_id or not MOMENT.fullmatch(since):
        return Response(status_code=400)
    posts = store.with_comment_counts(page.conn, store.new_activity(page.conn, page.pass_id, since, page.nsfw))
    latest = store.latest_comment_times(page.conn, [p.id for p in posts], not_by=page.pass_id)
    return render(page, "new-rows.html", posts=posts, latest_comments=latest)


def _event_stream(page, key: str) -> Response:
    queue = page.app.live.subscribe(key)
    return StreamingResponse(
        live.stream(page.app.live, key, queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


async def events(request: Request) -> Response:
    """Pings an open thread page when someone replies or reacts; the page then checks what it may see."""
    page = page_of(request)
    thread_id = request.path_params["id"]
    post = store.get_item(page.conn, thread_id)
    if page.pass_id is None or post is None or not post.is_post:
        return Response(status_code=404)
    return _event_stream(page, thread_id)


async def home_events(request: Request) -> Response:
    """Pings the front page when someone posts."""
    page = page_of(request)
    if page.pass_id is None:
        return Response(status_code=404)
    return _event_stream(page, live.HOME)


def notifications_json(request: Request) -> Response:
    """The bell's list. Which ones are unread is decided in the browser, so the server keeps no "last seen"."""
    page = page_of(request)
    if page.pass_id is None:
        return Response(status_code=401)
    return JSONResponse({"items": store.notifications(page.conn, page.pass_id)}, headers={"Cache-Control": "no-store"})


def notifications_page(request: Request) -> Response:
    """The same list as a plain page, for the bell without JavaScript."""
    page = page_of(request)
    if page.pass_id is None:
        return redirect("/sign-in")
    return render(page, "notifications.html", title="Feed", items=store.notifications(page.conn, page.pass_id))


async def bell_events(request: Request) -> Response:
    """Pings your bell when someone replies to you or reacts to something of yours."""
    page = page_of(request)
    if page.pass_id is None:
        return Response(status_code=404)
    return _event_stream(page, live.bell(page.pass_id))


routes = [
    Route("/thread/{id}", item),
    Route("/nsfw/thread/{id}", item),
    Route("/dates/thread/{id}", item),
    Route("/thread/{id}/events", events),
    Route("/events", home_events),
    Route("/new-activity", new_activity),
    Route("/notifications", notifications_page),
    Route("/notifications.json", notifications_json),
    Route("/notifications/events", bell_events),
]
