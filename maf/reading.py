"""Reading a thread: /thread/<id>, its view count and the comment tree."""

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import store
from .housetags import etiquette, is_hot, reply_placeholder
from .web import error_page, page_of, render


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
        "title": post.title,
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
        "flags": _flags(page, items),
        "requests": store.request_counts(page.conn, post.id),
        "notice": request.query_params.get("notice"),
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


routes = [Route("/thread/{id}", item)]
