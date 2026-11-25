"""Reading a thread: /thread/<id>, its view count and the comment tree."""

import re

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from . import live, markdown, store
from .housetags import etiquette, is_hot, reply_placeholder
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
    if page.pass_id and page.memory.count_view(page.pass_id, thread_id):
        store.increment_views(page.conn, thread_id)
        root = store.get_item(page.conn, item_id)

    items = store.thread_items(page.conn, thread_id, page.pass_id)
    post = next((i for i in items if i.id == thread_id), root)
    tree = store.build_tree(items, thread_id)
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
        "tree": tree,
        "label_of": label_of,
        "op_pass": op_pass,
        "my_label": page.labeler_label(thread_id, page.pass_id) if page.pass_id else None,
        "tags_list": tags,
        "hot": is_hot(tags),
        "etiquette_banner": etiquette(tags),
        "reply_placeholder": reply_placeholder(tags) if tags else "",
        "reactions": _reactions(page, items),
        "edits": store.thread_edits(page.conn, thread_id),
        "flags": _flags(page, items),
        "requests": store.request_counts(page.conn, post.id),
        "notice": request.query_params.get("notice"),
        # After the name check refused a reply or edit: which box "Post anyway" sends.
        "names_form": _names_form(request.query_params.get("names", "")),
        "body_class": "hottakes-thread" if is_hot(tags) else "",
    }
    return render(page, "item.html", **context)


def _reactions(page, items: list[store.Item]) -> dict[str, dict]:
    summary = {}
    for item in items:
        counts, mine = store.reaction_summary(page.conn, item.id, page.pass_id)
        summary[item.id] = {"counts": counts, "mine": mine}
    return summary


def _flags(page, items: list[store.Item]) -> dict[str, bool]:
    if not page.pass_id:
        return {}
    return {i.id: store.has_flagged(page.conn, page.pass_id, i.id) for i in items}


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
    Route("/thread/{id}/events", events),
    Route("/events", home_events),
    Route("/notifications", notifications_page),
    Route("/notifications.json", notifications_json),
    Route("/notifications/events", bell_events),
]
